"""Process-wide gateway locks (Dishka APP scope)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass(slots=True)
class GatewayLocks:
    """Shared locks for gateway request serialization."""

    agent_request: asyncio.Lock = field(default_factory=asyncio.Lock)
