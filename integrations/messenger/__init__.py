"""Platform-agnostic messenger integration primitives (Telegram, MAX, …)."""

from integrations.messenger.platform import MessengerPlatform
from integrations.messenger.platforms import MAX_PLATFORM, TELEGRAM_PLATFORM

__all__ = [
    "MAX_PLATFORM",
    "MessengerPlatform",
    "TELEGRAM_PLATFORM",
]