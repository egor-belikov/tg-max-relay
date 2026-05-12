"""Трансляция из привязанных Telegram-супергрупп в каналы Max: text, photo, video."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import requests

from .activity_log import log_event, text_preview
from .lessons_store import load_lessons, normalize_group, record_tg_to_max_relay
from .max_send import send_media_to_max_channel, send_to_max_channel
from .maxadmin_env import telegram_max_relay_bot_enabled, tg_to_max_relays_enabled
from .tg_relay_diag_log import log_relay_handlers_registered, relay_diag_log

MOSCOW = ZoneInfo("Europe/Moscow")

_map_cache: dict[str, Any] = {"ts": 0.0, "by_chat": {}}
_CACHE_TTL = 2.0

_CAPTION_MAX = 3500

_RELAY_CONTENT_TYPES = ("text", "photo", "video")


def _build_chat_index() -> dict[int, dict[str, Any]]:
    by: dict[int, dict[str, Any]] = {}
    data = load_lessons()
    for g in data.get("groups") or []:
        normalize_group(g)
        join = (g.get("join_url") or "").strip()
        spec = (g.get("telegram_relay_source") or "").strip()
        if not join or not spec:
            continue
        try:
            cid = int(spec)
        except ValueError:
            continue
        gid = str(g.get("id") or "")
        if not gid:
            continue
        floor = str(g.get("tg_relay_from_ts") or "").strip()
        by[cid] = {
            "group_id": gid,
            "join_url": join,
            "floor_iso": floor,
            "last_mid": int(g.get("relay_last_tg_mid") or 0),
        }
    return by


def _relay_index() -> dict[int, dict[str, Any]]:
    now = time.time()
    if (
        now - float(_map_cache.get("ts") or 0) < _CACHE_TTL
        and isinstance(_map_cache.get("by_chat"), dict)
    ):
        return _map_cache["by_chat"]
    idx = _build_chat_index()
    _map_cache["ts"] = now
    _map_cache["by_chat"] = idx
    return idx


def invalidate_relay_index() -> None:
    _map_cache["ts"] = 0.0


def _message_time_msk(message: Any) -> datetime:
    ts = getattr(message, "date", None)
    if ts is None:
        return datetime.now(MOSCOW)
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(MOSCOW)


def _after_connection_floor(message: Any, floor_iso: str) -> bool:
    if not (floor_iso or "").strip():
        return False
    try:
        fl = datetime.fromisoformat(floor_iso.replace("Z", "+00:00"))
        if fl.tzinfo is None:
            fl = fl.replace(tzinfo=MOSCOW)
        return _message_time_msk(message) >= fl.astimezone(MOSCOW)
    except Exception:
        return False


def _should_handle_relay(message: Any) -> bool:
    if not telegram_max_relay_bot_enabled() or not tg_to_max_relays_enabled():
        return False
    chat = getattr(message, "chat", None)
    if chat is None:
        return False
    ct = getattr(chat, "type", None)
    if ct not in ("group", "supergroup"):
        return False
    fu = getattr(message, "from_user", None)
    if fu is not None and getattr(fu, "is_bot", False):
        return False
    cid = getattr(chat, "id", None)
    if cid is None:
        return False
    try:
        icid = int(cid)
    except (TypeError, ValueError):
        return False
    return icid in _relay_index()


def _tg_token() -> str:
    t = (os.environ.get("API_TOKEN") or "").strip()
    if not t:
        raise RuntimeError("API_TOKEN не задан")
    return t


def _download_telegram_file(file_id: str) -> tuple[bytes, str]:
    base = f"https://api.telegram.org/bot{_tg_token()}"
    r = requests.get(f"{base}/getFile", params={"file_id": file_id}, timeout=60)
    j = r.json()
    if not j.get("ok"):
        raise RuntimeError(str(j.get("description") or "getFile"))
    fp = str(j["result"].get("file_path") or "").strip()
    if not fp or ".." in fp:
        raise RuntimeError("getFile: неверный file_path")
    name = fp.split("/")[-1] or "file.bin"
    url = f"https://api.telegram.org/file/bot{_tg_token()}/{fp}"
    resp = requests.get(url, timeout=300)
    resp.raise_for_status()
    return resp.content, name


def _caption(message: Any) -> str | None:
    c = getattr(message, "caption", None)
    if c is None:
        return None
    s = str(c).strip()
    if not s:
        return None
    return s[:_CAPTION_MAX] if len(s) > _CAPTION_MAX else s


def _largest_photo_file_id(message: Any) -> str | None:
    photos = getattr(message, "photo", None)
    if not photos:
        return None
    return max(photos, key=lambda p: getattr(p, "file_size", 0) or 0).file_id


def _relay_one_message(message: Any, info: dict[str, Any]) -> None:
    cid = int(message.chat.id)
    mid = int(getattr(message, "message_id", 0) or 0)
    join = str(info["join_url"])
    ct = getattr(message, "content_type", None) or ""
    cap = _caption(message)
    gid = str(info["group_id"])

    res: dict
    preview: str
    media_kind: str

    relay_diag_log(
        "relay_forward_start",
        group_id=gid,
        tg_chat_id=cid,
        tg_message_id=mid,
        content_type=ct,
        has_caption=bool(cap),
        max_join_preview=(join[:64] + "…") if len(join) > 64 else join,
    )

    try:
        if ct == "text":
            body = (getattr(message, "text", None) or "").strip()
            if not body:
                relay_diag_log(
                    "relay_skipped_empty_text",
                    group_id=gid,
                    tg_chat_id=cid,
                    tg_message_id=mid,
                )
                return
            if len(body) > _CAPTION_MAX:
                body = body[:_CAPTION_MAX]
            relay_diag_log("relay_max_text_send", group_id=gid, tg_message_id=mid, text_len=len(body))
            res = send_to_max_channel(join, body, markdown=False)
            preview = body
            media_kind = "text"
        elif ct == "photo":
            fid = _largest_photo_file_id(message)
            if not fid:
                relay_diag_log(
                    "relay_skipped_no_photo_file",
                    group_id=gid,
                    tg_message_id=mid,
                )
                return
            relay_diag_log("relay_tg_download_begin", group_id=gid, tg_message_id=mid, kind="photo")
            data, name = _download_telegram_file(fid)
            relay_diag_log(
                "relay_tg_download_ok",
                group_id=gid,
                tg_message_id=mid,
                kind="photo",
                bytes_len=len(data),
                filename=name[:120],
            )
            fn = name if "." in name else f"{name}.jpg"
            relay_diag_log("relay_max_media_send", group_id=gid, kind="photo", filename=fn[:120])
            res = send_media_to_max_channel(join, data, fn, cap)
            preview = cap or "[фото]"
            media_kind = "photo"
        elif ct == "video":
            v = getattr(message, "video", None)
            if v is None:
                relay_diag_log("relay_skipped_no_video_object", group_id=gid, tg_message_id=mid)
                return
            relay_diag_log("relay_tg_download_begin", group_id=gid, tg_message_id=mid, kind="video")
            data, name = _download_telegram_file(v.file_id)
            relay_diag_log(
                "relay_tg_download_ok",
                group_id=gid,
                tg_message_id=mid,
                kind="video",
                bytes_len=len(data),
                filename=name[:120],
            )
            fn = (getattr(v, "file_name", None) or "").strip() or name or "video.mp4"
            relay_diag_log("relay_max_media_send", group_id=gid, kind="video", filename=fn[:120])
            res = send_media_to_max_channel(join, data, fn, cap)
            preview = cap or "[видео]"
            media_kind = "video"
        else:
            relay_diag_log(
                "relay_skipped_unsupported_type",
                group_id=gid,
                tg_message_id=mid,
                content_type=ct,
            )
            return
    except Exception as e:
        err_s = f"{type(e).__name__}: {e}"[:400]
        relay_diag_log(
            "relay_pipeline_error",
            group_id=gid,
            tg_chat_id=cid,
            tg_message_id=mid,
            content_type=ct,
            error=err_s,
        )
        record_tg_to_max_relay(
            gid,
            tg_message_id=mid,
            text_preview=f"{ct}: {err_s}"[:400],
            ok=False,
            max_mid=None,
            error=err_s[:300],
            media_kind=ct,
        )
        invalidate_relay_index()
        log_event(
            "tg_to_max_relay_fail",
            group_id=gid,
            tg_chat_id=cid,
            tg_message_id=mid,
            ok=False,
            error=err_s[:300],
            content_type=ct,
        )
        return

    ok = bool(res.get("ok"))
    if ok:
        relay_diag_log(
            "relay_max_post_ok",
            group_id=gid,
            tg_chat_id=cid,
            tg_message_id=mid,
            media_kind=media_kind,
            max_mid=str(res.get("mid") or ""),
            max_message_url=(str(res.get("message_url") or "")[:200] or None),
        )
    else:
        err = str(res.get("error") or "unknown")[:400]
        relay_diag_log(
            "relay_max_post_fail",
            group_id=gid,
            tg_chat_id=cid,
            tg_message_id=mid,
            media_kind=media_kind,
            error=err,
            max_unavailable_hint="проверьте права бота в канале Max и MAX_API_TOKEN",
        )

    record_tg_to_max_relay(
        gid,
        tg_message_id=mid,
        text_preview=preview,
        ok=ok,
        max_mid=str(res.get("mid") or "") if res.get("mid") else None,
        error=str(res.get("error") or "") if not ok else None,
        media_kind=media_kind,
    )
    invalidate_relay_index()
    log_event(
        "tg_to_max_relay_ok" if ok else "tg_to_max_relay_fail",
        group_id=gid,
        tg_chat_id=cid,
        tg_message_id=mid,
        ok=ok,
        max_mid=res.get("mid"),
        error=res.get("error"),
        text_preview=text_preview(preview),
        media_kind=media_kind,
    )


def register_handlers(bot: Any, **_kw: Any) -> None:
    @bot.message_handler(
        content_types=list(_RELAY_CONTENT_TYPES),
        func=_should_handle_relay,
    )
    def on_group_relay(message: Any) -> None:
        chat = message.chat
        cid = int(chat.id)
        mid = int(getattr(message, "message_id", 0) or 0)
        ct = getattr(message, "content_type", None) or ""

        relay_diag_log(
            "relay_tg_message_in_supergroup",
            tg_chat_id=cid,
            tg_message_id=mid,
            content_type=ct,
            chat_type=getattr(chat, "type", None),
            chat_title=(str(getattr(chat, "title", "") or "")[:120] or None),
        )

        info = _relay_index().get(cid)
        if not info:
            relay_diag_log(
                "relay_skipped_chat_not_in_max_lessons_map",
                tg_chat_id=cid,
                tg_message_id=mid,
                hint="нет telegram_relay_source+join_url в max_lessons или неверный id",
            )
            return

        floor = info.get("floor_iso") or ""
        if not (floor or "").strip():
            relay_diag_log(
                "relay_skipped_no_bind_timestamp",
                tg_chat_id=cid,
                group_id=info["group_id"],
                tg_message_id=mid,
                hint="сохраните привязку в /maxadmin чтобы выставить tg_relay_from_ts",
            )
            return

        if not _after_connection_floor(message, floor):
            relay_diag_log(
                "relay_skipped_message_before_bind_time",
                tg_chat_id=cid,
                group_id=info["group_id"],
                tg_message_id=mid,
                message_ts_msk=_message_time_msk(message).isoformat(),
                bind_floor_iso=floor,
            )
            return

        if mid <= int(info.get("last_mid") or 0):
            relay_diag_log(
                "relay_skipped_already_relayed_message",
                tg_chat_id=cid,
                group_id=info["group_id"],
                tg_message_id=mid,
                relay_last_tg_mid=info.get("last_mid"),
            )
            return

        _relay_one_message(message, info)

    mapped = len(_build_chat_index())
    log_relay_handlers_registered(mapped)
    print(f"[tg_to_max_relay] handlers registered (mapped chats={mapped})", flush=True)
