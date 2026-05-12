"""Флаги веб-панели /maxadmin и трансляции сообщений из Telegram-групп в каналы Max."""

from __future__ import annotations

import os


def _env_flag(name: str, *, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    s = str(v).strip().lower()
    if not s:
        return default
    return s in ("1", "true", "yes", "on")


def tg_to_max_relays_enabled() -> bool:
    """
    Мастер-выключатель трансляции TG→Max (сообщения из привязанных супергрупп в каналы Max).
    Выключить: ENABLE_TG_TO_MAX_RELAY=0.
    """
    v = os.environ.get("ENABLE_TG_TO_MAX_RELAY")
    if v is None:
        return True
    s = str(v).strip().lower()
    if not s:
        return True
    return s in ("1", "true", "yes", "on")


def maxadmin_enabled() -> bool:
    """
    Веб-панель /maxadmin и фоновые посты custom:* (reminder_worker при ENABLE_MAX_AUTOPOST).
    Выключить: ENABLE_MAXADMIN=0.
    """
    return _env_flag("ENABLE_MAXADMIN", default=True)


def telegram_max_relay_bot_enabled() -> bool:
    """
    Регистрация хендлеров трансляции в основном Telegram-боте (@kinodolgoletiebot).
    Выключить: ENABLE_TELEGRAM_MAX_RELAY_BOT=0.
    """
    return _env_flag("ENABLE_TELEGRAM_MAX_RELAY_BOT", default=True)
