"""When the agent may create/hot-reload extensions and change system settings.

**Allowed**

- Local single-operator: CLI, TUI, ``holix run``.
- Messenger (Telegram/MAX): **bot admin only** (host sets ``operator_scope``).

**Denied**

- Messenger end-users (not the bot admin).
- Unattended runs with no operator flag.

Override with env::

    HOLIX_SELF_EXTENSIONS=1   # force allow (all users — not for shared bots)
    HOLIX_SELF_EXTENSIONS=0   # force deny (even admin)

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
    """Whether *this* run may create / hot-reload extensions and edit system settings."""
    override = _env_bool_override()
    if override is not None:
        return override

    if is_messenger_multi_user_runtime():
        try:
            from core.tools.execution_context import is_operator_actor

            return is_operator_actor() is True
        except Exception:
            return False

    if agent is not None:
        cfg = getattr(agent, "config", None)
        flag = getattr(cfg, "self_extensions_enabled", None)
        if flag is False:
            return False
    return True


def self_extension_denied_message() -> str:
    return (
        "Changing agent extensions and system settings is allowed for the **operator** "
        "(local CLI/TUI) or the **Telegram/MAX bot admin** only. "
        "Regular messenger users cannot create, enable, disable, reload, or edit "
        "extension settings. Ask the admin, or use a local Holix session. "
        "Emergency override: HOLIX_SELF_EXTENSIONS=1 (not for shared bots)."
    )
