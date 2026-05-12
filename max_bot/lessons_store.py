"""Только загрузка/сохранение max_lessons и учёт релея TG→Max."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import data as data_module

MOSCOW = ZoneInfo("Europe/Moscow")
_lock = threading.RLock()


def _default_data() -> dict[str, Any]:
    return {"version": 1, "groups": []}


def load_lessons() -> dict[str, Any]:
    data_module.ensure_max_lessons_available()
    p = data_module.MAX_LESSONS_PATH
    if not p.exists():
        return _default_data()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return _default_data()
        raw.setdefault("version", 1)
        raw.setdefault("groups", [])
        return raw
    except Exception:
        return _default_data()


def save_lessons(data: dict[str, Any]) -> None:
    data_module.MAX_LESSONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        data_module.MAX_LESSONS_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def normalize_group(g: dict[str, Any]) -> dict[str, Any]:
    g.setdefault("section", "")
    g.setdefault("title", "Без названия")
    g.setdefault("lesson_title", g.get("title", "Занятие"))
    g.setdefault("join_url", "")
    g.setdefault("chat_id", None)
    g.setdefault("instructors", "")
    g.setdefault("zoom_url", "")
    g.setdefault("meeting_id", "")
    g.setdefault("telegram_relay_source", "")
    g.setdefault("tg_relay_from_ts", "")
    g.setdefault("relay_last_tg_mid", 0)
    g.setdefault("relay_broadcast_log", [])
    g.setdefault("slots", [])
    g.setdefault("skipped_dates", [])
    g.setdefault("post_log", {})
    g.setdefault("post_plans", {})
    r = g.setdefault("reminders", {})
    r.setdefault("evening_before_time", "19:00")
    r.setdefault("morning_same_day_time", "09:00")
    r.setdefault("evening_class_start_hour", 17)
    r.setdefault("minutes_before_evening", 30)
    r.setdefault("minutes_before_daytime", 5)
    for s in g.get("slots") or []:
        s.setdefault("id", str(uuid.uuid4())[:8])
        s.setdefault("weekdays", [1, 3])
        s.setdefault("start", "10:00")
        s.setdefault("end", "11:00")
        s.setdefault("zoom_url", "")
        s.setdefault("meeting_id", "")
    return g


_RELAY_LOG_CAP = 80


def record_tg_to_max_relay(
    group_id: str,
    *,
    tg_message_id: int,
    text_preview: str,
    ok: bool,
    max_mid: str | None,
    error: str | None,
    media_kind: str | None = None,
) -> None:
    with _lock:
        data = load_lessons()
        for g in data.get("groups") or []:
            if str(g.get("id")) != group_id:
                continue
            normalize_group(g)
            prev = int(g.get("relay_last_tg_mid") or 0)
            g["relay_last_tg_mid"] = max(prev, tg_message_id)
            log = g.get("relay_broadcast_log")
            if not isinstance(log, list):
                log = []
            entry = {
                "ts": datetime.now(MOSCOW).isoformat(timespec="seconds"),
                "kind": "tg_to_max",
                "tg_message_id": tg_message_id,
                "preview": (text_preview or "")[:500],
                "media": (media_kind or "")[:40],
                "ok": ok,
                "max_mid": max_mid or "",
                "error": (error or "")[:300] if error else "",
            }
            log.append(entry)
            while len(log) > _RELAY_LOG_CAP:
                log.pop(0)
            g["relay_broadcast_log"] = log
            save_lessons(data)
            return
