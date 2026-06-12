"""Subprocess entry for `holix tui --web` (textual-serve launches this module)."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> None:
    args = list(argv if argv is not None else sys.argv[1:])
    profile = "default"
    i = 0
    while i < len(args):
        if args[i] in ("-p", "--profile") and i + 1 < len(args):
            profile = args[i + 1]
            i += 2
            continue
        if args[i].startswith("--profile="):
            profile = args[i].split("=", 1)[1]
        i += 1

    from cli.tui.app import run_tui

    run_tui(profile=profile)


if __name__ == "__main__":
    main()