"""Helix documentation website (web-docs/) — path resolution, build, serve."""

from __future__ import annotations

import http.server
import json
import os
import socketserver
import subprocess
import sys
import urllib.error
import urllib.request
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
        "web-docs/ not found. Run from the Helix repository or reinstall HelixAgentAi."
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


def bootstrap_docs_env(profile: str | None = None) -> str:
    """Load profile ``.env`` so docs chat flags from ``profiles/<name>/.env`` apply."""
    from core.env_loader import active_profile_name, bootstrap_profile_env

    name = (profile or active_profile_name() or "default").strip() or "default"
    bootstrap_profile_env(name)
    return name


def _env_bool(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _docs_chat_public_config() -> dict:
    bootstrap_docs_env()
    token = os.getenv("HELIX_DOCS_CHAT_TOKEN", "").strip()
    return {
        "enabled": bool(_env_bool("HELIX_DOCS_CHAT_ENABLED") and token),
        "proxyPath": "/api/docs-chat",
        "configPath": "/api/docs-chat/config.json",
        "sessionPath": "/api/docs-chat/session",
    }


def _gateway_docs_chat_base(profile: str | None = None) -> str:
    """Resolve gateway API base for docs-chat proxy (prefer live gateway state)."""
    from cli.services.gateway_state import load_state

    name = bootstrap_docs_env(profile)
    state = load_state(name)
    if state is not None:
        host = state.host
        if host in ("0.0.0.0", "::"):
            host = "127.0.0.1"
        return f"http://{host}:{state.port}/v1/docs/chat"

    host = os.getenv("HELIX_GATEWAY_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.getenv("HELIX_GATEWAY_PORT", "8000"))
    return f"http://{host}:{port}/v1/docs/chat"


def _gateway_docs_chat_url() -> str:
    return _gateway_docs_chat_base()


def _docs_chat_token() -> str:
    bootstrap_docs_env()
    return os.getenv("HELIX_DOCS_CHAT_TOKEN", "").strip()


def _open_docs_chat_request(
    body: bytes,
    headers: dict[str, str],
    *,
    method: str = "POST",
    url: str | None = None,
) -> urllib.request.Request:
    token = _docs_chat_token()
    req_headers = {"Authorization": f"Bearer {token}"}
    if method == "POST":
        req_headers.update(
            {
                "Content-Type": headers.get("Content-Type", "application/json"),
                "Accept": headers.get("Accept", "text/event-stream"),
            }
        )
    return urllib.request.Request(
        url or _gateway_docs_chat_url(),
        data=body if method != "GET" else None,
        method=method,
        headers=req_headers,
    )


def _proxy_gateway_response(
    handler: http.server.SimpleHTTPRequestHandler,
    req: urllib.request.Request,
    *,
    timeout: float = 30,
) -> None:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            handler.send_response(resp.status)
            content_type = resp.headers.get("Content-Type", "application/json")
            handler.send_header("Content-Type", content_type)
            handler.send_header("Cache-Control", "no-store")
            handler.end_headers()
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                handler.wfile.write(chunk)
                handler.wfile.flush()
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        content_type = exc.headers.get("Content-Type", "application/json")
        handler.send_response(exc.code)
        handler.send_header("Content-Type", content_type)
        handler.end_headers()
        handler.wfile.write(payload)
    except urllib.error.URLError as exc:
        payload = json.dumps({"detail": f"Gateway unreachable: {exc.reason}"}).encode()
        handler.send_response(503)
        handler.send_header("Content-Type", "application/json")
        handler.end_headers()
        handler.wfile.write(payload)


def run_docs_server_forever(
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    web_docs_dir: Path | None = None,
    quiet: bool = False,
    profile: str | None = None,
) -> None:
    """Serve the static documentation site until interrupted."""
    active_profile = bootstrap_docs_env(profile)
    root = web_docs_dir or resolve_web_docs_dir()
    index = root / "index.html"
    if not index.is_file():
        raise FileNotFoundError(f"Missing {index}")

    if not (root / "search-index.json").is_file():
        if not quiet:
            print_info("search-index.json missing — running build…")
        build_docs_site(root)

    class DocsHandler(http.server.SimpleHTTPRequestHandler):
        docs_profile = active_profile

        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def log_message(self, format: str, *args) -> None:
            if not quiet and console.is_interactive:
                super().log_message(format, *args)

        def _docs_chat_disabled(self) -> bool:
            return not _env_bool("HELIX_DOCS_CHAT_ENABLED") or not _docs_chat_token()

        def _spa_index_path(self, path: str) -> str | None:
            clean = path.split("?", 1)[0].rstrip("/") or "/"
            if clean.startswith("/api/"):
                return None
            if clean.startswith("/assets/") or clean.startswith("/content/"):
                return None
            # Static files (json, md, xml, …) must not be replaced with index.html.
            if "." in Path(clean).name:
                return None
            if clean in {"/", "/docs"} or clean.startswith("/docs/"):
                return "/index.html"
            return None

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0].rstrip("/")
            if path == "/api/docs-chat/config.json":
                payload = json.dumps(_docs_chat_public_config(), ensure_ascii=False).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)
                return
            if path == "/api/docs-chat/session":
                if self._docs_chat_disabled():
                    self.send_response(404)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"detail":"Docs chat disabled"}')
                    return
                query = self.path.split("?", 1)[1] if "?" in self.path else ""
                req = _open_docs_chat_request(
                    b"",
                    {},
                    method="GET",
                    url=f"{_gateway_docs_chat_base(self.docs_profile)}/session?{query}",
                )
                _proxy_gateway_response(self, req)
                return
            spa_index = self._spa_index_path(self.path)
            if spa_index is not None:
                self.path = spa_index
            super().do_GET()

        def do_POST(self) -> None:
            if self.path.rstrip("/") != "/api/docs-chat":
                self.send_error(404)
                return
            if self._docs_chat_disabled():
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"detail":"Docs chat disabled"}')
                return

            length = int(self.headers.get("Content-Length", "0") or 0)
            body = self.rfile.read(length) if length else b""
            req = _open_docs_chat_request(
                body,
                {
                    "Content-Type": self.headers.get("Content-Type", "application/json"),
                    "Accept": self.headers.get("Accept", "text/event-stream"),
                },
            )
            _proxy_gateway_response(self, req, timeout=120)

        def do_DELETE(self) -> None:
            path = self.path.split("?", 1)[0].rstrip("/")
            if path != "/api/docs-chat/session":
                self.send_error(404)
                return
            if self._docs_chat_disabled():
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"detail":"Docs chat disabled"}')
                return
            query = self.path.split("?", 1)[1] if "?" in self.path else ""
            req = _open_docs_chat_request(
                b"",
                {},
                method="DELETE",
                url=f"{_gateway_docs_chat_base(self.docs_profile)}/session?{query}",
            )
            _proxy_gateway_response(self, req)

        def do_OPTIONS(self) -> None:
            path = self.path.split("?", 1)[0].rstrip("/")
            if path in {"/api/docs-chat", "/api/docs-chat/config.json", "/api/docs-chat/session"}:
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")
                self.end_headers()
                return
            self.send_error(404)

    if quiet:
        print(f"Helix docs → {docs_url(host, port)}", flush=True)

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((host, port), DocsHandler) as httpd:
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