"""Tests for API error mapping."""

import pytest
from fastapi import HTTPException

from api.errors import agent_error_to_http, openai_error_body


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