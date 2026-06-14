"""Entry point: holix max / gateway MAX polling companion."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os

from integrations.max.config import load_max_settings
from integrations.max.polling import run_polling

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


async def run_bot(profile: str = "default") -> None:
    settings = load_max_settings(profile)
    if settings.is_webhook_mode:
        raise RuntimeError(
            "HELIX_MAX_MODE=webhook — используйте `holix gateway start` "
            "(Long Polling только для dev/test через gateway)."
        )
    await run_polling(settings, profile=profile)


def main(profile: str = "default") -> None:
    asyncio.run(run_bot(profile))


if __name__ == "__main__":
    from core.platform_compat import ensure_multiprocessing_support

    ensure_multiprocessing_support()

    parser = argparse.ArgumentParser(description="Holix MAX Long Polling worker")
    parser.add_argument("--profile", default=os.environ.get("HOLIX_PROFILE", "default"))
    cli_args = parser.parse_args()
    os.environ["HOLIX_PROFILE"] = cli_args.profile
    main(cli_args.profile)