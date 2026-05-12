"""Структурированные логи Max (очередь постов, автопост, проверка каналов). Файл в DATA_DIR."""

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
_MAX_BYTES = 8 * 1024 * 1024
_BACKUP_COUNT = 5
_TEXT_PREVIEW = 600


def _enabled() -> bool:
    return os.environ.get("ENABLE_MAX_ACTIVITY_LOG", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def text_preview(s: str | None, n: int = _TEXT_PREVIEW) -> str:
    t = (s or "").replace("\r", " ").replace("\n", " ").strip()
    if len(t) > n:
        return t[:n] + "…"
    return t


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


def log_event(event: str, **fields: Any) -> None:
    """Одна строка JSON (JSONL) в max_bot_activity.log."""
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
        p = data_module.MAX_BOT_ACTIVITY_LOG_PATH
        p.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            if p.exists() and p.stat().st_size > _MAX_BYTES:
                _rotate(p)
            with open(p, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass


def log_probe_cache_invalidate() -> None:
    log_event("probe_cache_invalidate")


def log_channel_probe_batch(
    fresh: dict[str, dict[str, Any]],
    prev: dict[str, dict[str, Any]],
) -> None:
    """
    Логируем только потерю доступа после ранее успешного подключения.

    Это убирает стартовый шум вида "None -> not connected" и регулярные повторы
    по неподключенным каналам.
    """
    for url, st in fresh.items():
        o = prev.get(url) or {}
        # До первого успешного/неуспешного снапшота по ссылке ничего не логируем.
        if not o:
            continue
        was_connected = bool(o.get("ok") and o.get("can_post"))
        is_connected = bool(st.get("ok") and st.get("can_post"))
        if not was_connected or is_connected:
            continue
        log_event(
            "channel_probe_disconnected",
            join_url=url,
            ok=st.get("ok"),
            can_post=st.get("can_post"),
            detail=st.get("detail"),
            chat_title=st.get("chat_title"),
            previous_ok=o.get("ok"),
            previous_can_post=o.get("can_post"),
            previous_detail=o.get("detail"),
        )
