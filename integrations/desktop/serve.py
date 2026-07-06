"""Run Holix Studio sidecar (uvicorn)."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import uvicorn

from integrations.desktop.app import create_studio_app
from integrations.desktop.security import StudioSecurityPolicy, append_query_token
from integrations.desktop.workspace_files import (
    STUDIO_WORKSPACE_CWD,
    normalize_studio_workspace_mode,
    resolve_studio_workspace_root,
)


async def _shutdown_app(app) -> None:
    session = getattr(app.state, "studio_session", None)
    if session is not None:
        await session.shutdown()


def run_studio_server(
    profile: str,
    policy: StudioSecurityPolicy,
    *,
    port: int = 8788,
    headless: bool = False,
    open_browser: bool = False,
    serve_cwd: Path | str | None = None,
    workspace_mode: str = STUDIO_WORKSPACE_CWD,
) -> None:
    mode = normalize_studio_workspace_mode(workspace_mode)
    launch_cwd = Path(serve_cwd or Path.cwd()).expanduser().resolve()
    workspace_root = resolve_studio_workspace_root(
        profile,
        mode=mode,
        serve_cwd=launch_cwd,
    )
    if mode == STUDIO_WORKSPACE_CWD:
        os.chdir(workspace_root)
    app = create_studio_app(
        policy,
        profile,
        serve_cwd=launch_cwd,
        workspace_mode=mode,
        workspace_root=workspace_root,
    )
    url = f"http://{policy.host}:{port}/studio/"
    if policy.token:
        url = append_query_token(url, policy.token)

    from cli.utils.rich_console import print_info, print_success, print_warning

    print_success(f"Holix Studio serving profile={profile!r}")
    print_info(f"Workspace mode: {mode}")
    print_info(f"Workspace root: {workspace_root}")
    print_info(f"URL: {url}")
    if policy.token_generated:
        print_warning("Ephemeral Studio token — save the URL; required for API/WS access")
    if headless:
        print_info("Headless mode (no browser)")

    if open_browser and not headless:
        import webbrowser

        webbrowser.open(url)

    config = uvicorn.Config(
        app,
        host=policy.host,
        port=port,
        log_level="info",
        lifespan="on",
    )
    server = uvicorn.Server(config)

    async def _serve() -> None:
        await server.serve()

    try:
        asyncio.run(_serve())
    except KeyboardInterrupt:
        pass
    finally:
        try:
            asyncio.run(_shutdown_app(app))
        except Exception:
            pass