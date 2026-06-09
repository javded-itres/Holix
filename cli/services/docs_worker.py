"""Standalone docs server for gateway supervisor: ``python -m cli.services.docs_worker``."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    import os

    parser = argparse.ArgumentParser(description="Helix documentation HTTP server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument(
        "--profile",
        default=os.environ.get("HELIX_PROFILE", "default"),
        help="Helix profile whose .env supplies docs-chat settings",
    )
    args = parser.parse_args(argv)

    from cli.services.docs_site import run_docs_server_forever

    try:
        run_docs_server_forever(
            host=args.host,
            port=args.port,
            quiet=True,
            profile=args.profile,
        )
    except KeyboardInterrupt:
        pass
    except OSError:
        return 1
    return 0


if __name__ == "__main__":
    from core.platform_compat import ensure_multiprocessing_support

    ensure_multiprocessing_support()
    sys.exit(main())