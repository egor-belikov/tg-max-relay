"""Пути данных для релея TG→Max (том DATA_DIR на сервере совпадает с kinodolgoletie_data)."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", SCRIPT_DIR))

MAX_LESSONS_PATH = DATA_DIR / "max_lessons.json"
TG_MAX_RELAY_DIAG_LOG_PATH = DATA_DIR / "tg_max_relay_diag.jsonl"
MAX_BOT_ACTIVITY_LOG_PATH = DATA_DIR / "max_bot_activity.log"


def ensure_max_lessons_available() -> None:
    """Копирует max_lessons.json из образа в DATA_DIR при первом запуске."""
    src = SCRIPT_DIR / "max_lessons.json"
    if not src.is_file():
        return
    MAX_LESSONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not MAX_LESSONS_PATH.exists():
        shutil.copy(src, MAX_LESSONS_PATH)
        return
    try:
        raw = json.loads(MAX_LESSONS_PATH.read_text(encoding="utf-8"))
        if raw.get("groups"):
            return
    except Exception:
        pass
    shutil.copy(src, MAX_LESSONS_PATH)
