#!/usr/bin/env python3
"""Serve Helix documentation site locally."""

from __future__ import annotations

import argparse
import http.server
import socketserver
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve Helix web-docs")
    parser.add_argument("--port", "-p", type=int, default=8080)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(ROOT), **kw)

    with socketserver.TCPServer((args.host, args.port), Handler) as httpd:
        url = f"http://{args.host}:{args.port}/"
        print(f"Helix docs → {url}")
        print("Press Ctrl+C to stop")
        httpd.serve_forever()


if __name__ == "__main__":
    main()