#!/usr/bin/env python3
"""Cross-platform Holix installer (run before ``holix`` is on PATH).

Usage:
    python scripts/install.py
    python scripts/install.py --system
    python scripts/install.py --extra telegram --extra browser
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from repo without installing the package first
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from cli.installer import (  # noqa: E402
    InstallOptions,
    detect_repo_root,
    install_holix,
    verify_holix_on_path,
)
from cli.installer.system import record_install  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install Holix CLI globally")
    parser.add_argument(
        "--system",
        action="store_true",
        help="Install for all users (may need sudo / Administrator)",
    )
    parser.add_argument(
        "--no-path",
        action="store_true",
        help="Do not update shell PATH",
    )
    parser.add_argument(
        "--extra",
        action="append",
        default=[],
        metavar="NAME",
        help="Optional dependency group (telegram, browser)",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="Holix repository path (default: parent of scripts/)",
    )
    args = parser.parse_args(argv)

    try:
        repo_root = detect_repo_root(args.repo) if args.repo else detect_repo_root(_REPO)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    opts = InstallOptions(
        repo_root=repo_root,
        scope="system" if args.system else "user",
        update_path=not args.no_path,
        extras=tuple(args.extra),
    )

    print(f"Installing Holix from {repo_root} …")
    result = install_holix(opts)
    print(result.message)
    if not result.success:
        return 1

    record_install(result, opts, repo_root=repo_root)

    ok, loc = verify_holix_on_path()
    if ok:
        print(f"OK: holix found at {loc}")
    else:
        print("Note: open a new terminal and run: holix version")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())