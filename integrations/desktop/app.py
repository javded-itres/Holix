"""Standalone FastAPI app for ``holix studio serve``."""

from __future__ import annotations

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from integrations.desktop.router import create_studio_router
from integrations.desktop.security import StudioSecurityPolicy


def create_studio_app(policy: StudioSecurityPolicy, profile: str) -> FastAPI:
    app = FastAPI(
        title="Holix Studio",
        description="Local Holix Studio sidecar (chat + workspace IDE)",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1", "http://localhost"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    router = create_studio_router(profile=profile, auth_token=policy.token or None)
    app.include_router(router)
    app.state.studio_session = router.studio_session  # type: ignore[attr-defined]
    return app