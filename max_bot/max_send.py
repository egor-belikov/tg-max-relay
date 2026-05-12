"""Отправка сообщений в канал Max по ссылке-приглашению (join URL)."""

from __future__ import annotations

import asyncio
import os
from typing import Any


def _token() -> str:
    t = (os.environ.get("MAX_API_TOKEN") or os.environ.get("MAX_BOT_TOKEN") or "").strip()
    if not t:
        raise RuntimeError("MAX_API_TOKEN не задан")
    return t


def unpack_max_send_response(send_result: Any) -> dict[str, str | None]:
    """
    Bot.send_message в maxapi возвращает SendedMessage с полем message;
    реальные url и body.mid находятся у внутреннего Message.
    """
    inner = getattr(send_result, "message", None)
    msg_obj = inner if inner is not None else send_result
    url = getattr(msg_obj, "url", None)
    body = getattr(msg_obj, "body", None)
    mid = getattr(body, "mid", None) if body is not None else None
    return {
        "message_url": str(url).strip() if url else None,
        "mid": str(mid).strip() if mid is not None else None,
    }


async def _send_media_buffer_async(
    join_url: str,
    data: bytes,
    filename: str,
    caption: str | None,
) -> dict:
    """Загрузка файла в Max и отправка в канал по join URL (фото/видео/файл)."""
    from maxapi import Bot
    from maxapi.types.input_media import InputMediaBuffer

    from .max_join import get_chat_by_join_url

    bot = Bot(token=_token())
    chat = await get_chat_by_join_url(bot, join_url.strip())
    imb = InputMediaBuffer(buffer=data, filename=filename or "file.bin")
    att = await bot.upload_media(imb)
    cap = (caption or "").strip()
    msg = await bot.send_message(
        chat_id=chat.chat_id,
        text=cap if cap else "",
        attachments=[att],
    )
    u = unpack_max_send_response(msg)
    return {
        "ok": True,
        "chat_id": chat.chat_id,
        "message_url": u["message_url"],
        "mid": u["mid"],
    }


def send_media_to_max_channel(
    join_url: str,
    data: bytes,
    filename: str,
    caption: str | None = None,
) -> dict:
    """Синхронно: байты файла (как из Telegram getFile) + опциональная подпись."""
    try:
        return asyncio.run(
            _send_media_buffer_async(
                join_url.strip(),
                data,
                filename,
                caption,
            )
        )
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


async def _send_async(join_url: str, text: str, *, parse_mode: Any | None = None) -> dict:
    from maxapi import Bot

    from .max_join import get_chat_by_join_url

    bot = Bot(token=_token())
    chat = await get_chat_by_join_url(bot, join_url)
    chat_id = chat.chat_id
    kwargs: dict[str, Any] = {"chat_id": chat_id, "text": text}
    if parse_mode is not None:
        kwargs["parse_mode"] = parse_mode
    msg = await bot.send_message(**kwargs)
    u = unpack_max_send_response(msg)
    return {
        "ok": True,
        "chat_id": chat_id,
        "message_url": u["message_url"],
        "mid": u["mid"],
    }


def send_to_max_channel(join_url: str, text: str, *, markdown: bool = False) -> dict:
    """
    Синхронная отправка. Возвращает dict с ok, message_url, mid или ok=False, error.
    """
    from maxapi.enums.parse_mode import ParseMode  # type: ignore

    parse_mode = ParseMode.MARKDOWN if markdown else None
    try:
        return asyncio.run(_send_async(join_url.strip(), text, parse_mode=parse_mode))
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


async def send_to_max_channel_async(join_url: str, text: str, *, markdown: bool = False) -> dict:
    from maxapi.enums.parse_mode import ParseMode  # type: ignore

    parse_mode = ParseMode.MARKDOWN if markdown else None
    try:
        return await _send_async(join_url.strip(), text, parse_mode=parse_mode)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
