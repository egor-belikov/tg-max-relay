"""
Единственный клиент Telegram getUpdates для API_TOKEN.
Апдейты пересылаются в контейнер kinodolgoletie (POST /internal/telegram-update),
где pyTelegramBotAPI обрабатывает хендлеры, включая TG→Max relay.

Иначе два процесса с infinity_polling на один токен дают 409 Conflict.
"""

from __future__ import annotations

import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

API_TOKEN = (os.environ.get("API_TOKEN") or "").strip()
SECRET = (os.environ.get("INTERNAL_TELEGRAM_POLLER_SECRET") or "").strip()
FORWARD_URL = (
    os.environ.get("TELEGRAM_UPDATE_FORWARD_URL") or "http://kinodolgoletie:8080/internal/telegram-update"
).strip()
TG_API = (os.environ.get("TELEGRAM_API_URL", "").strip().rstrip("/") or "https://api.telegram.org").rstrip("/")
TIMEOUT_GET = int(os.environ.get("TELEGRAM_GETUPDATES_TIMEOUT", "50"))


def main() -> None:
    if not API_TOKEN:
        print("[tg-poller] ERROR: API_TOKEN не задан", flush=True)
        sys.exit(1)
    if not SECRET:
        print("[tg-poller] ERROR: INTERNAL_TELEGRAM_POLLER_SECRET не задан", flush=True)
        sys.exit(1)

    base = f"{TG_API}/bot{API_TOKEN}"
    # Снять webhook, иначе getUpdates недоступен.
    try:
        r = requests.get(f"{base}/deleteWebhook", params={"drop_pending_updates": False}, timeout=30)
        print(f"[tg-poller] deleteWebhook status={r.status_code}", flush=True)
    except Exception as e:
        print(f"[tg-poller] deleteWebhook: {e}", flush=True)

    get_updates = f"{base}/getUpdates"
    offset: int | None = 0
    print(f"[tg-poller] forward → {FORWARD_URL}", flush=True)

    while True:
        try:
            params: dict[str, str | int] = {"timeout": TIMEOUT_GET}
            if offset is not None:
                params["offset"] = offset
            r = requests.get(get_updates, params=params, timeout=TIMEOUT_GET + 15)
            if r.status_code != 200:
                print(f"[tg-poller] getUpdates HTTP {r.status_code}: {r.text[:300]}", flush=True)
                time.sleep(2)
                continue
            j = r.json()
            if not j.get("ok"):
                print(f"[tg-poller] getUpdates not ok: {j}", flush=True)
                time.sleep(2)
                continue
            for u in j.get("result") or []:
                uid = u.get("update_id")
                if isinstance(uid, int):
                    offset = uid + 1
                try:
                    fr = requests.post(
                        FORWARD_URL,
                        json=u,
                        headers={"X-Telegram-Poller-Secret": SECRET},
                        timeout=120,
                    )
                    if fr.status_code not in (204, 200):
                        print(
                            f"[tg-poller] forward HTTP {fr.status_code} update_id={uid} body={fr.text[:200]}",
                            flush=True,
                        )
                except Exception as e:
                    print(f"[tg-poller] forward error update_id={uid}: {e}", flush=True)
        except requests.RequestException as e:
            print(f"[tg-poller] request error: {e}", flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()
