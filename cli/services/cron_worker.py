"""Standalone cron worker for gateway --reload mode: ``python -m cli.services.cron_worker``."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from core.cron.scheduler import CronScheduler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Holix cron scheduler worker")
    parser.add_argument("--profile", default=os.environ.get("HOLIX_PROFILE", "default"))
    args = parser.parse_args(argv)
    os.environ["HOLIX_PROFILE"] = args.profile

    async def _run() -> None:
        await CronScheduler(args.profile).run_forever()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    from core.platform_compat import ensure_multiprocessing_support

    ensure_multiprocessing_support()
    sys.exit(main())