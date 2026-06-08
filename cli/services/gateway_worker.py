"""Background worker entry: ``python -m cli.services.gateway_worker``."""

from __future__ import annotations

import argparse
import os
import sys

from cli.services.gateway_state import LOG_PATH, clear_state, new_state, save_state
from cli.services.supervisor import run_gateway_supervisor


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Helix gateway background worker")
    from config import settings

    parser.add_argument("--host", default=settings.gateway_host)
    parser.add_argument("--port", type=int, default=settings.gateway_port)
    parser.add_argument("--profile", default="default")
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--with-docs", action="store_true")
    parser.add_argument("--docs-host", default=settings.docs_host)
    parser.add_argument("--docs-port", type=int, default=settings.docs_port)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    from core.logging.setup import configure_helix_logging

    configure_helix_logging()
    args = _parse_args(argv)
    from core.env_loader import bootstrap_profile_env

    bootstrap_profile_env(args.profile)

    def _env_bool(name: str) -> bool:
        return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}

    with_docs = args.with_docs or _env_bool("HELIX_GATEWAY_WITH_DOCS") or _env_bool(
        "HELIX_GATEWAY_DOCS"
    )
    docs_host = args.docs_host or os.getenv("HELIX_DOCS_HOST", "127.0.0.1")
    docs_port = args.docs_port
    if not args.with_docs:
        raw_port = os.getenv("HELIX_DOCS_PORT", "").strip()
        if raw_port.isdigit():
            docs_port = int(raw_port)

    save_state(
        new_state(
            pid=os.getpid(),
            host=args.host,
            port=args.port,
            profile=args.profile,
            reload=args.reload,
        )
    )

    try:
        run_gateway_supervisor(
            args.host,
            args.port,
            reload=args.reload,
            profile=args.profile,
            with_docs=with_docs,
            docs_host=docs_host,
            docs_port=docs_port,
        )
    finally:
        clear_state(args.profile)
    return 0


if __name__ == "__main__":
    from core.platform_compat import ensure_multiprocessing_support

    ensure_multiprocessing_support()
    sys.exit(main())