"""Entry point: holix telegram."""

from __future__ import annotations

import asyncio

from integrations.telegram.bot import HolixTelegramBot
from integrations.telegram.config import load_telegram_settings


async def run_bot(profile: str = "default") -> None:
    settings = load_telegram_settings(profile)
    bot = HolixTelegramBot(settings, profile=profile)
    await bot.run_polling()


def main(profile: str = "default") -> None:
    asyncio.run(run_bot(profile))


if __name__ == "__main__":
    import argparse
    import os

    from core.platform_compat import ensure_multiprocessing_support

    ensure_multiprocessing_support()
    parser = argparse.ArgumentParser(description="Holix Telegram bot")
    parser.add_argument(
        "--profile",
        "-p",
        default=(os.getenv("HOLIX_PROFILE") or "default").strip() or "default",
    )
    args = parser.parse_args()
    main(args.profile)