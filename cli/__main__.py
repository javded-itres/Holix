"""Allow ``python -m cli`` / ``uv run python -m cli`` as the Helix CLI entry."""

from cli.main import main

if __name__ == "__main__":
    main()