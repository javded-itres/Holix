#!/usr/bin/env python3
"""Serve Helix documentation site locally (with docs-chat API proxy)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve Helix web-docs")
    parser.add_argument("--port", "-p", type=int, default=8080)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--profile", default="default")
    args = parser.parse_args()

    from cli.services.docs_site import run_docs_server_forever

    run_docs_server_forever(
        host=args.host,
        port=args.port,
        profile=args.profile,
    )


if __name__ == "__main__":
    main()