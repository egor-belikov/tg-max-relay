"""Подробный JSONL-лог трансляции Telegram → Max (отдельно от max_bot_activity.log)."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import data as data_module

_lock = threading.Lock()
_MOSCOW = ZoneInfo("Europe/Moscow")
_MAX_BYTES = 16 * 1024 * 1024
_BACKUP_COUNT = 3


def _enabled() -> bool:
    return os.environ.get("ENABLE_TG_MAX_RELAY_DIAG_LOG", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _path() -> Path:
    return data_module.TG_MAX_RELAY_DIAG_LOG_PATH


def _rotate(path: Path) -> None:
    last = path.with_name(f"{path.name}.{_BACKUP_COUNT}")
    if last.exists():
        last.unlink()
    for i in range(_BACKUP_COUNT - 1, 0, -1):
        a = path.with_name(f"{path.name}.{i}")
        b = path.with_name(f"{path.name}.{i + 1}")
        if a.exists():
            a.rename(b)
    if path.exists():
        path.rename(path.with_name(f"{path.name}.1"))


def relay_diag_log(event: str, **fields: Any) -> None:
    """Одна строка JSON в tg_max_relay_diag.jsonl."""
    if not _enabled():
        return
    rec: dict[str, Any] = {
        "ts": datetime.now(_MOSCOW).isoformat(timespec="seconds"),
        "event": event,
    }
    for k, v in fields.items():
        if v is not None:
            rec[k] = v
    line = json.dumps(rec, ensure_ascii=False, default=str) + "\n"
    try:
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            if p.exists() and p.stat().st_size > _MAX_BYTES:
                _rotate(p)
            with open(p, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass


def log_relay_probe_snapshot(
    groups: list[dict[str, Any]],
    tg_meta: dict[str, dict[str, Any]],
    max_meta: dict[str, dict[str, Any]],
) -> None:
    """После «Обновить проверки» на maxadmin: состояние TG и Max по каждой строке."""
    for g in groups:
        gid = str(g.get("id") or "")
        title = str(g.get("title") or g.get("lesson_title") or "")
        spec = (g.get("telegram_relay_source") or "").strip()
        join = (g.get("join_url") or "").strip()
        tgm = tg_meta.get(spec) if spec else {}
        relay_diag_log(
            "relay_probe_tg",
            group_id=gid,
            group_title=title[:120],
            tg_chat_spec_preview=(spec[:24] + "…") if len(spec) > 24 else spec,
            tg_probe_state=tgm.get("state"),
            tg_probe_detail=(str(tgm.get("detail") or "")[:300] or None),
            tg_from_cache=tgm.get("from_cache"),
        )
        mm = max_meta.get(join) or {}
        relay_diag_log(
            "relay_probe_max",
            group_id=gid,
            group_title=title[:120],
            max_join_preview=(join[:56] + "…") if len(join) > 56 else join,
            max_ok=mm.get("ok"),
            max_can_post=mm.get("can_post"),
            max_detail=(str(mm.get("detail") or "")[:300] or None),
            max_chat_title=(str(mm.get("chat_title") or "")[:120] or None),
        )


def log_relay_handlers_registered(mapped_chats: int) -> None:
    relay_diag_log(
        "relay_handlers_ready",
        mapped_supergroups=mapped_chats,
        telegram_max_relay_bot=os.environ.get("ENABLE_TELEGRAM_MAX_RELAY_BOT", "1"),
        tg_to_max_master=os.environ.get("ENABLE_TG_TO_MAX_RELAY", "1"),
    )
