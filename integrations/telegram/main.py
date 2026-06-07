"""Entry point: helix telegram."""

from __future__ import annotations

import asyncio

from integrations.telegram.bot import HelixTelegramBot
from integrations.telegram.config import load_telegram_settings


async def run_bot(profile: str = "default") -> None:
    settings = load_telegram_settings(profile)
    bot = HelixTelegramBot(settings, profile=profile)
    await bot.run_polling()


def main(profile: str = "default") -> None:
    asyncio.run(run_bot(profile))


if __name__ == "__main__":
    from core.platform_compat import ensure_multiprocessing_support

    ensure_multiprocessing_support()
    main()