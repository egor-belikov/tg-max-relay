"""
Отдельный процесс: только long polling Telegram и релей TG→Max.
Тот же API_TOKEN, что у kinodolgoletiebot; основной контейнер kinodolgoletie
должен иметь ENABLE_TELEGRAM_MAX_RELAY_BOT=0, иначе два polling на один токен.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()

import telebot  # noqa: E402

TELEGRAM_API_BASE = (
    os.environ.get("TELEGRAM_API_URL", "").strip().rstrip("/") or "https://api.telegram.org"
).rstrip("/")
if TELEGRAM_API_BASE != "https://api.telegram.org":
    telebot.apihelper.API_URL = f"{TELEGRAM_API_BASE}/bot{{0}}/{{1}}"

API_TOKEN = (os.environ.get("API_TOKEN") or "").strip()


def _telegram_delete_webhook_if_any(bot_obj: telebot.TeleBot) -> None:
    if not getattr(bot_obj, "token", ""):
        return
    try:
        ok = bot_obj.delete_webhook(drop_pending_updates=False)
        print(f"[tg-max-relay] delete_webhook: {'ok' if ok else 'no'}", flush=True)
    except Exception as e:
        print(f"[tg-max-relay] delete_webhook: {e}", flush=True)


def main() -> None:
    if not API_TOKEN:
        print("[tg-max-relay] ERROR: API_TOKEN не задан", flush=True)
        sys.exit(1)

    bot = telebot.TeleBot(API_TOKEN)
    try:
        from max_bot.tg_to_max_relay import register_handlers as register_tg_to_max_relay

        register_tg_to_max_relay(bot)
    except Exception as e:
        print(f"[tg-max-relay] register handlers failed: {e}", flush=True)
        raise

    _telegram_delete_webhook_if_any(bot)
    print("[tg-max-relay] infinity_polling start", flush=True)
    bot.infinity_polling(skip_pending=False)


if __name__ == "__main__":
    main()
