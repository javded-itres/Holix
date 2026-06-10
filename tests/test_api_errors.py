"""Tests for API error mapping."""

from api.errors import agent_error_to_http, openai_error_body
from fastapi import HTTPException

from config import settings


def test_openai_error_body_shape():
    body = openai_error_body("failed", error_type="server_error", code="internal_error")
    assert body["error"]["message"] == "failed"
    assert body["error"]["type"] == "server_error"


def test_agent_error_maps_confirmation():
    exc = agent_error_to_http(Exception("Confirmation denied for tool"))
    assert exc.status_code == 409
    assert exc.detail["error"]["code"] == "confirmation_denied"


def test_agent_error_passes_through_http_exception():
    original = HTTPException(status_code=418, detail="teapot")
    assert agent_error_to_http(original) is original


def test_agent_error_hides_details_when_debug_disabled(monkeypatch):
    monkeypatch.setattr(settings, "log_debug_enabled", False)
    exc = agent_error_to_http(Exception("Confirmation denied for tool"))
    assert exc.status_code == 409
    assert exc.detail["error"]["message"] == "Internal server error"


def test_agent_error_shows_details_when_debug_enabled(monkeypatch):
    monkeypatch.setattr(settings, "log_debug_enabled", True)
    exc = agent_error_to_http(Exception("Confirmation denied for tool"))
    assert exc.detail["error"]["message"] == "Confirmation denied for tool"