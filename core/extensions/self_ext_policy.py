"""When the agent may create/hot-reload its own drop-in extensions.

**Allowed (local single-operator):** CLI, TUI, ``holix run``, local studio-style use.

**Denied (multi-user / group bots):** Telegram/MAX bots and other messenger hosts
serving many end-users — extensions must not be authored into shared agent state.

Override with env::

    HOLIX_SELF_EXTENSIONS=1   # force allow
    HOLIX_SELF_EXTENSIONS=0   # force deny

Messenger hosts set ``HOLIX_MESSENGER_HOST=telegram|max``.
"""

from __future__ import annotations

import os
import sys
from typing import Any


def _env_bool_override() -> bool | None:
    raw = (os.environ.get("HOLIX_SELF_EXTENSIONS") or "").strip().lower()
    if not raw:
        return None
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return None


def is_messenger_multi_user_runtime() -> bool:
    """True when this process (or request context) serves messenger end-users."""
    host = (os.environ.get("HOLIX_MESSENGER_HOST") or "").strip().lower()
    if host in {"telegram", "max", "messenger", "1", "true", "yes"}:
        return True
    # argv heuristic (supervisor: python -m integrations.telegram.main)
    joined = " ".join(sys.argv).lower()
    if "integrations.telegram" in joined or "integrations.max" in joined:
        return True
    try:
        from core.tools.execution_context import get_chat_delivery_bridge

        if get_chat_delivery_bridge() is not None:
            return True
    except Exception:
        pass
    return False


def agent_allows_self_extensions(agent: Any | None = None) -> bool:
    """Whether *this* agent may create / hot-reload self-authored extensions."""
    override = _env_bool_override()
    if override is not None:
        return override

    if agent is not None:
        cfg = getattr(agent, "config", None)
        flag = getattr(cfg, "self_extensions_enabled", None)
        if flag is False:
            return False
        if flag is True:
            # still respect messenger process
            if is_messenger_multi_user_runtime():
                return False
            return True

    if is_messenger_multi_user_runtime():
        return False
    return True


def self_extension_denied_message() -> str:
    return (
        "Self-authored agent extensions are only allowed in **local** single-operator mode "
        "(CLI / TUI / holix run). "
        "This agent serves a multi-user messenger (Telegram/MAX or chat delivery bridge). "
        "Create extensions only on a local profile, not for group bots. "
        "Override (not recommended on shared bots): HOLIX_SELF_EXTENSIONS=1"
    )
