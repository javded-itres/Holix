"""Run Holix Studio sidecar (uvicorn)."""

from __future__ import annotations

import asyncio

import uvicorn

from integrations.desktop.app import create_studio_app
from integrations.desktop.security import StudioSecurityPolicy, append_query_token


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
) -> None:
    app = create_studio_app(policy, profile)
    url = f"http://{policy.host}:{port}/studio/"
    if policy.token:
        url = append_query_token(url, policy.token)

    from cli.utils.rich_console import print_info, print_success, print_warning

    print_success(f"Holix Studio serving profile={profile!r}")
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