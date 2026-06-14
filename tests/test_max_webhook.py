"""MAX webhook and gateway integration tests."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from integrations.max.config import MaxSettings
from integrations.max.constants import WEBHOOK_PATH, WEBHOOK_SECRET_HEADER
from integrations.max.gateway_routes import (
    MaxGatewayState,
    init_max_webhook,
    register_max_routes,
    reload_max_webhook,
    shutdown_max_webhook,
)
from integrations.max.webhook import MaxWebhookHandler


def _webhook_settings(**overrides: object) -> MaxSettings:
    base = {
        "access_token": "test-token-1234567890",
        "allowed_user_ids": "42",
        "profile": "default",
        "mode": "webhook",
        "webhook_url": "https://example.com/max/webhook",
        "webhook_secret": "s3cret",
    }
    base.update(overrides)
    return MaxSettings(**base)  # type: ignore[arg-type]


def test_webhook_handler_secret_validation() -> None:
    settings = _webhook_settings()
    handler = MaxWebhookHandler(settings)

    assert handler.verify_secret("s3cret") is True
    assert handler.verify_secret("wrong") is False
    assert handler.verify_secret(None) is False


def test_webhook_handler_allows_missing_secret_when_not_configured() -> None:
    settings = _webhook_settings(webhook_secret="")
    handler = MaxWebhookHandler(settings)
    assert handler.verify_secret(None) is True


@pytest.mark.asyncio
async def test_register_max_routes_accepts_valid_update() -> None:
    settings = _webhook_settings()
    handler = MaxWebhookHandler(settings)
    handler.handle_update = AsyncMock()  # type: ignore[method-assign]

    import integrations.max.gateway_routes as routes

    routes._state = MaxGatewayState(
        settings=settings,
        handler=handler,
        client=AsyncMock(),
        subscribed=True,
    )

    app = FastAPI()
    register_max_routes(app)
    client = TestClient(app)

    update = {
        "update_type": "message_created",
        "message": {
            "sender": {"user_id": 42},
            "body": {"text": "ping"},
            "recipient": {"user_id": 42},
        },
    }
    response = client.post(
        WEBHOOK_PATH,
        json=update,
        headers={WEBHOOK_SECRET_HEADER: "s3cret"},
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}

    await asyncio.sleep(0.05)
    handler.handle_update.assert_awaited_once_with(update)
    routes._state = None


def test_register_max_routes_rejects_bad_secret() -> None:
    settings = _webhook_settings()
    handler = MaxWebhookHandler(settings)

    import integrations.max.gateway_routes as routes

    routes._state = MaxGatewayState(
        settings=settings,
        handler=handler,
        client=AsyncMock(),
        subscribed=True,
    )

    app = FastAPI()
    register_max_routes(app)
    client = TestClient(app)
    response = client.post(WEBHOOK_PATH, json={"update_type": "bot_started"}, headers={})
    assert response.status_code == 403
    routes._state = None


def test_register_max_routes_returns_503_when_not_configured() -> None:
    import integrations.max.gateway_routes as routes

    routes._state = None
    app = FastAPI()
    register_max_routes(app)
    client = TestClient(app)
    response = client.post(WEBHOOK_PATH, json={"update_type": "bot_started"})
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_init_max_webhook_registers_subscription(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("integrations.max.gateway_routes.load_max_env_files", lambda: None)

    settings = _webhook_settings()
    with patch(
        "integrations.max.gateway_routes.load_max_settings",
        return_value=settings,
    ):
        with patch(
            "integrations.max.gateway_routes.register_webhook",
            new_callable=AsyncMock,
            return_value=True,
        ) as register:
            with patch(
                "integrations.max.gateway_routes.MaxClient",
            ) as client_cls:
                client = AsyncMock()
                client_cls.return_value = client
                with patch(
                    "integrations.max.bot.create_agent",
                    new_callable=AsyncMock,
                    return_value=MagicMock(model="m"),
                ):
                    state = await init_max_webhook("default")
                    await shutdown_max_webhook()

    assert state is not None
    assert state.subscribed is True
    register.assert_awaited_once()


@pytest.mark.asyncio
async def test_reload_max_webhook_reregisters(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("integrations.max.gateway_routes.load_max_env_files", lambda: None)

    settings = _webhook_settings()
    with patch(
        "integrations.max.gateway_routes.load_max_settings",
        return_value=settings,
    ):
        with patch(
            "integrations.max.gateway_routes.register_webhook",
            new_callable=AsyncMock,
            return_value=True,
        ):
            with patch(
                "integrations.max.gateway_routes.unregister_webhook",
                new_callable=AsyncMock,
            ):
                with patch(
                    "integrations.max.gateway_routes.MaxClient",
                ) as client_cls:
                    client = AsyncMock()
                    client_cls.return_value = client
                    with patch(
                        "integrations.max.bot.create_agent",
                        new_callable=AsyncMock,
                        return_value=MagicMock(model="m"),
                    ):
                        result = await reload_max_webhook("default")
                        await shutdown_max_webhook()

    assert result["max_webhook"] is True
    assert result["max_configured"] is True


@pytest.mark.asyncio
async def test_init_max_webhook_skips_polling_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("integrations.max.gateway_routes.load_max_env_files", lambda: None)

    settings = _webhook_settings(mode="polling")
    with patch(
        "integrations.max.gateway_routes.load_max_settings",
        return_value=settings,
    ):
        state = await init_max_webhook("default")
    assert state is None