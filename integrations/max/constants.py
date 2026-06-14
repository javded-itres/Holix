"""Shared constants for MAX integration."""

from __future__ import annotations

WEBHOOK_SECRET_HEADER = "X-Max-Bot-Api-Secret"
WEBHOOK_PATH = "/max/webhook"

UPDATE_TYPES = [
    "bot_started",
    "message_created",
    "message_callback",
]