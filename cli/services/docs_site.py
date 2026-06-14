"""Holix documentation website — path resolution, build, serve."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

from cli.installer.system import detect_repo_root
from cli.utils.rich_console import console, print_error, print_info, print_success


def resolve_web_docs_dir() -> Path:
    """Locate holix-docs/ (standalone site) or legacy web-docs/ in a checkout."""
    candidates: list[Path] = []

    override = os.getenv("HOLIX_WEB_DOCS_DIR", "").strip()
    if override:
        candidates.append(Path(override).expanduser())

    try:
        repo = detect_repo_root()
        candidates.append(repo.parent / "holix-docs")
        candidates.append(repo / "web-docs")
    except FileNotFoundError:
        pass

    candidates.append(Path(__file__).resolve().parents[2] / "web-docs")
    candidates.append(Path.cwd() / "holix-docs")
    candidates.append(Path.cwd() / "web-docs")

    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if (resolved / "index.html").is_file():
            return resolved

    raise FileNotFoundError(
        "Documentation site not found. Clone holix-docs next to Helix, set "
        "HOLIX_WEB_DOCS_DIR, or run from a checkout that contains web-docs/."
    )


def _sync_docs_from_helix(web_docs_dir: Path) -> int:
    """Copy markdown from Helix docs/en and docs/ru into the site content/."""
    try:
        repo = detect_repo_root()
    except FileNotFoundError:
        return 0

    copied = 0
    for lang in ("en", "ru"):
        src = repo / "docs" / lang
        if not src.is_dir():
            continue
        dst = web_docs_dir / "content" / lang
        dst.mkdir(parents=True, exist_ok=True)
        for md in src.glob("*.md"):
            shutil.copy2(md, dst / md.name)
            copied += 1
    return copied


def build_docs_site(web_docs_dir: Path | None = None) -> Path:
    """Sync markdown from Helix docs/ (when available) and rebuild search index."""
    root = web_docs_dir or resolve_web_docs_dir()
    script = root / "build.py"
    if not script.is_file():
        raise FileNotFoundError(f"Missing build script: {script}")

    synced = _sync_docs_from_helix(root)
    if synced:
        print_info(f"Synced {synced} markdown files from Helix docs/")
    print_info("Building documentation index…")
    subprocess.run(
        [sys.executable, str(script)],
        cwd=str(root),
        check=True,
        timeout=120,
    )
    print_success(f"Documentation built: {root}")
    return root


def docs_url(host: str, port: int) -> str:
    return f"http://{host}:{port}/"


def bootstrap_docs_env(profile: str | None = None) -> str:
    """Load profile ``.env`` so docs chat flags from ``profiles/<name>/.env`` apply."""
    from core.env_loader import active_profile_name, bootstrap_profile_env

    name = (profile or active_profile_name() or "default").strip() or "default"
    bootstrap_profile_env(name)
    return name


def run_docs_server_forever(
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    web_docs_dir: Path | None = None,
    quiet: bool = False,
    profile: str | None = None,
) -> None:
    """Serve the static documentation site until interrupted."""
    bootstrap_docs_env(profile)
    root = web_docs_dir or resolve_web_docs_dir()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from holix_docs.server import run_server_forever

    run_server_forever(
        host=host,
        port=port,
        web_root=root,
        quiet=quiet,
        profile=profile,
    )


def serve_docs_site(
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    open_browser: bool = False,
    web_docs_dir: Path | None = None,
) -> None:
    """Serve the static documentation site until interrupted (interactive CLI)."""
    url = docs_url(host, port)
    console.print()
    print_success(f"Holix documentation → [link={url}]{url}[/link]")
    console.print("[dim]Press Ctrl+C to stop[/dim]")
    console.print()

    if open_browser:
        webbrowser.open(url)

    try:
        run_docs_server_forever(host=host, port=port, web_docs_dir=web_docs_dir)
    except KeyboardInterrupt:
        console.print("\n[dim]Documentation server stopped.[/dim]")
    except OSError as e:
        print_error(f"Could not bind {host}:{port} — {e}")
        raise SystemExit(1) from e