"""
Разрешение канала Max по инвайт-ссылке (https://max.ru/join/…).

Платформа отвечает на часть путей вида GET /chats/<строка> ошибкой
`method.not.found` (хэш начинается с цифры, «_» и т.д.), поэтому
**нельзя** опираться на один запрос с инвайт-хэшем в URL.

Рабочий способ: **GET /chats** (пагинация) — список групповых чатов, где уже
участвует бот; у каждого чата есть поле `link`. Сопоставляем сохранённую
ссылку или инвайт-хэш с `chat.link`, получаем `chat_id` (int) для отправки.

См. https://dev.max.ru/docs-api/methods/GET/chats
"""

from __future__ import annotations

import re
import threading
import time
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from maxapi import Bot
    from maxapi.types.chats import Chat
else:
    Chat = Any  # lazy maxapi import avoids circular init with maxapi during partial package load

_JOIN_RE = re.compile(
    r"(?:https?://)?(?:www\.)?max\.ru/join/([^/?#]+)",
    re.IGNORECASE,
)

_lock = threading.Lock()
_chats_cache_ts = 0.0
_chats_cache_list: list[Chat] | None = None
CHATS_LIST_TTL_SEC = 75.0


def extract_join_token(url_or_token: str) -> str | None:
    """Инвайт-хэш из `/join/…` или уже переданный хэш."""
    from urllib.parse import unquote

    s = (url_or_token or "").strip()
    if not s:
        return None
    m = _JOIN_RE.search(s)
    if m:
        return unquote(m.group(1))
    if re.match(r"^[A-Za-z0-9_.\-]+$", s) and len(s) >= 8:
        return s
    return None


def _norm_link(s: str) -> str:
    s = (s or "").strip().rstrip("/")
    if s.startswith("http://"):
        s = "https://" + s[7:]
    if s.startswith("max.ru/"):
        s = "https://" + s
    return s


def build_link_index(chats: list[Chat]) -> dict[str, Chat]:
    """Ключи: нормализованный link; «token:<хэш>»."""
    out: dict[str, Chat] = {}
    for c in chats:
        ln = c.link
        if not ln:
            continue
        n = _norm_link(ln)
        out[n] = c
        tok = extract_join_token(ln)
        if tok:
            out[f"token:{tok}"] = c
    return out


def lookup_chat_in_index(join_url: str, index: dict[str, Chat]) -> Chat | None:
    nu = _norm_link(join_url)
    if nu in index:
        return index[nu]
    tok = extract_join_token(join_url)
    if tok and f"token:{tok}" in index:
        return index[f"token:{tok}"]
    return None


async def fetch_all_chats(bot: Bot) -> list[Chat]:
    """Все страницы GET /chats (до лимита итераций)."""
    out: list[Chat] = []
    marker = None
    for _ in range(400):
        batch = await bot.get_chats(count=100, marker=marker)
        out.extend(batch.chats or [])
        marker = batch.marker
        if marker is None:
            break
    return out


async def get_or_load_chats_with_index(bot: Bot) -> tuple[list[Chat], dict[str, Chat]]:
    """Кэш списка чатов на короткое время, чтобы не дергать API на каждое сообщение."""
    global _chats_cache_ts, _chats_cache_list
    now = time.time()
    with _lock:
        stale = _chats_cache_list is None or (now - _chats_cache_ts >= CHATS_LIST_TTL_SEC)
        if not stale:
            lst = _chats_cache_list or []
            return lst, build_link_index(lst)
    chats = await fetch_all_chats(bot)
    with _lock:
        _chats_cache_list = chats
        _chats_cache_ts = time.time()
    return chats, build_link_index(chats)


def invalidate_chats_cache() -> None:
    """Сброс кэша списка чатов (например после «Обновить» на панели)."""
    global _chats_cache_ts, _chats_cache_list
    with _lock:
        _chats_cache_list = None
        _chats_cache_ts = 0.0


async def get_chat_by_join_url(bot: Bot, join_url: str) -> Chat:
    """Найти чат по инвайт-ссылке среди чатов бота (GET /chats)."""
    _, index = await get_or_load_chats_with_index(bot)
    chat = lookup_chat_in_index(join_url, index)
    if chat is None:
        raise ValueError(
            "Канал не найден среди чатов бота (GET /chats). "
            "Добавьте бота в канал и проверьте, что ссылка совпадает с приглашением канала."
        )
    return cast(Chat, chat)
