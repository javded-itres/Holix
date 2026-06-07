"""Send cron job results to Telegram chat."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def send_telegram_notification(
    chat_id: int,
    message: str,
    *,
    bot_token: str | None = None,
    parse_mode: str = "HTML",
) -> bool:
    """Send a message to Telegram chat using aiogram Bot."""
    try:
        from aiogram import Bot
    except ImportError:
        logger.warning("aiogram not installed, cannot send Telegram notification")
        return False

    if not bot_token:
        from integrations.telegram.config import load_telegram_settings

        settings = load_telegram_settings()
        bot_token = settings.bot_token

    if not bot_token:
        logger.warning("Telegram bot token not configured")
        return False

    bot = Bot(token=bot_token)
    try:
        await bot.send_message(chat_id, message, parse_mode=parse_mode)
        return True
    except Exception as e:
        logger.warning("Failed to send Telegram notification: %s", e)
        return False
    finally:
        try:
            await bot.session.close()
        except Exception:
            pass


def format_status_message(
    *,
    session_name: str,
    model: str,
    profile: str,
    mode: str,
    active_tasks: list[str] | None = None,
    timestamp: str | None = None,
) -> str:
    """Format a status update message for Telegram."""
    lines = [
        "🔔 <b>Helix Agent Status</b>",
        "",
        f"📌 <b>Сессия:</b> <code>{session_name}</code>",
        f"🤖 <b>Модель:</b> <code>{model}</code>",
        f"👤 <b>Профиль:</b> <code>{profile}</code>",
        f"⚙️ <b>Режим:</b> <code>{mode}</code>",
    ]

    if active_tasks:
        lines.extend(["", "📋 <b>Активные задачи:</b>"])
        for i, task in enumerate(active_tasks, 1):
            lines.append(f"  {i}. {task}")
    else:
        lines.extend(["", "✅ <i>Нет активных задач</i>"])

    if timestamp:
        lines.extend(["", f"<i>🕐 {timestamp}</i>"])

    return "\n".join(lines)