"""Helix documentation website (web-docs/) — path resolution, build, serve."""

from __future__ import annotations

import http.server
import socketserver
import subprocess
import sys
import webbrowser
from pathlib import Path

from cli.installer.system import detect_repo_root
from cli.utils.rich_console import console, print_error, print_info, print_success


def resolve_web_docs_dir() -> Path:
    """Locate web-docs/ in a wheel install or source checkout."""
    candidates: list[Path] = []

    try:
        import config

        candidates.append(Path(config.__file__).resolve().parent / "web-docs")
    except Exception:
        pass

    try:
        candidates.append(detect_repo_root() / "web-docs")
    except FileNotFoundError:
        pass

    candidates.append(Path(__file__).resolve().parents[2] / "web-docs")
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
        "web-docs/ not found. Run from the Helix repository or reinstall helix-agent-ai."
    )


def build_docs_site(web_docs_dir: Path | None = None) -> Path:
    """Rebuild search index and copy markdown from docs/."""
    root = web_docs_dir or resolve_web_docs_dir()
    script = root / "build.py"
    if not script.is_file():
        raise FileNotFoundError(f"Missing build script: {script}")

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


def run_docs_server_forever(
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    web_docs_dir: Path | None = None,
    quiet: bool = False,
) -> None:
    """Serve the static documentation site until interrupted."""
    root = web_docs_dir or resolve_web_docs_dir()
    index = root / "index.html"
    if not index.is_file():
        raise FileNotFoundError(f"Missing {index}")

    if not (root / "search-index.json").is_file():
        if not quiet:
            print_info("search-index.json missing — running build…")
        build_docs_site(root)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def log_message(self, format: str, *args) -> None:
            if not quiet and console.is_interactive:
                super().log_message(format, *args)

    if quiet:
        print(f"Helix docs → {docs_url(host, port)}", flush=True)

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((host, port), Handler) as httpd:
        httpd.serve_forever()


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
    print_success(f"Helix documentation → [link={url}]{url}[/link]")
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