"""Cron auto-create from natural language (disabled).

Previously Holix intercepted chat messages like «каждый день в 10…» and created
gateway cron jobs *before* the agent ran. That also fired on build briefs such as
«создай сервис, который раз в 5 минут…», which must be implemented as code.

Scheduling is explicit only:
- user: ``/cron add …`` or CLI ``holix cron add``
- agent: ``schedule_cron`` tool when the user asked Holix to run the *agent* on a schedule
"""

from __future__ import annotations

from typing import Any


async def try_cron_auto_dispatch(host: Any, message: str) -> bool:
    """No-op: do not auto-create cron from free-form chat."""
    del host, message
    return False
