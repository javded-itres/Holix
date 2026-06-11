"""Profile-bound agent soul — ``SOUL.md`` in ``~/.helix/profiles/<name>/``."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core.env_loader import profile_dir_path

SOUL_MD_FILENAME = "SOUL.md"
SOUL_MESSAGE_TYPE = "agent_soul"
DEFAULT_MAX_CHARS = 12_000

DEFAULT_SOUL_MD = """# Agent Soul

This file defines who you are across every session. Edit it to shape personality,
values, and behavior. Helix reloads it on each new session and after context compression.

## Identity

You are a capable, honest assistant. You think step-by-step, admit uncertainty,
and prioritize the user's goals over performative answers.

## Values

- Clarity over verbosity
- Correctness over speed when stakes are high
- Respect boundaries, secrets, and workspace isolation

## Communication

- Match the user's language unless they ask otherwise
- Use structure (lists, headings) for complex answers
- Confirm assumptions before destructive actions
"""

PLACEHOLDER_SOUL_MD = """# Agent Soul

_Personality and values will be defined during your first conversation with the user._
"""

_IDENTITY_SAVE_HINT = """
## Saving agent soul / personality

When the user asks to **save**, **remember**, or **store** their preferred agent personality,
soul, identity, character, **душу**, **личность**, or similar — call `save_agent_soul` with the
description. If SOUL.md is still empty or placeholder, the tool writes the full soul; otherwise it **appends**.
""".strip()


def soul_path(profile: str | None = None) -> Path:
    name = (profile or "default").strip() or "default"
    return profile_dir_path(name) / SOUL_MD_FILENAME


def _read_raw_soul(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _normalize_soul_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def is_soul_empty_or_placeholder(profile: str | None = None) -> bool:
    raw = _read_raw_soul(soul_path(profile))
    if not raw:
        return True
    norm = _normalize_soul_text(raw)
    for template in (PLACEHOLDER_SOUL_MD, DEFAULT_SOUL_MD):
        if norm == _normalize_soul_text(template):
            return True
    if norm in {
        _normalize_soul_text("# Agent Soul"),
        _normalize_soul_text("# Agent Soul _Personality and values will be defined during your first conversation with the user._"),
    }:
        return True
    return False


def ensure_soul_file(profile: str | None = None, *, placeholder: bool = False) -> Path:
    """Create ``SOUL.md`` when missing."""
    path = soul_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        body = PLACEHOLDER_SOUL_MD if placeholder else DEFAULT_SOUL_MD
        path.write_text(body.strip() + "\n", encoding="utf-8")
    return path


def bootstrap_profile_identity(profile: str | None = None) -> None:
    """First-run files: INIT.md + placeholder SOUL.md."""
    from core.profile.init import ensure_init_file

    ensure_init_file(profile)
    ensure_soul_file(profile, placeholder=True)


def update_soul_content(
    profile: str | None,
    content: str,
    *,
    section: str | None = None,
) -> str:
    """Write full soul when empty/placeholder; otherwise append."""
    path = soul_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)

    body = (content or "").strip()
    if not body:
        raise ValueError("Soul content is empty")

    if section:
        body = f"## {section.strip()}\n\n{body}"

    if is_soul_empty_or_placeholder(profile):
        if not body.startswith("#"):
            body = f"# Agent Soul\n\n{body}"
        path.write_text(body.strip() + "\n", encoding="utf-8")
        return "written"

    existing = _read_raw_soul(path)
    path.write_text(existing.rstrip() + "\n\n" + body.strip() + "\n", encoding="utf-8")
    return "appended"


def load_soul_md(
    profile: str | None = None,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str:
    """Read soul from disk (creates default only when init is not pending)."""
    from core.profile.init import init_pending

    path = soul_path(profile)
    if not path.is_file():
        if init_pending(profile):
            ensure_soul_file(profile, placeholder=True)
        else:
            ensure_soul_file(profile, placeholder=False)

    text = _read_raw_soul(path)
    if not text:
        text = PLACEHOLDER_SOUL_MD if init_pending(profile) else DEFAULT_SOUL_MD.strip()
    elif is_soul_empty_or_placeholder(profile) and init_pending(profile):
        text = PLACEHOLDER_SOUL_MD.strip()

    if len(text) > max_chars:
        text = (
            text[:max_chars]
            + f"\n\n… [truncated; full file: profiles/{profile or 'default'}/{SOUL_MD_FILENAME}]"
        )
    return text


def format_soul_block(profile: str | None = None) -> str:
    body = load_soul_md(profile)
    name = (profile or "default").strip() or "default"
    return (
        f"## Agent Soul (profiles/{name}/{SOUL_MD_FILENAME})\n"
        "This is your persistent identity for this Helix profile. "
        "Follow it in every reply; it reloads from disk on new sessions and after compression.\n\n"
        f"{body}"
    )


def format_identity_instructions(profile: str | None = None) -> str:
    from core.profile.init import init_pending

    parts = [_IDENTITY_SAVE_HINT]
    if init_pending(profile):
        from core.profile.init import format_init_block

        init_block = format_init_block(profile)
        if init_block:
            parts.insert(0, init_block)
    return "\n\n".join(parts)


def build_soul_message(profile: str | None = None) -> dict[str, Any]:
    return {
        "role": "system",
        "content": format_soul_block(profile),
        "metadata": {"type": SOUL_MESSAGE_TYPE, "pinned": True},
    }


def is_soul_message(message: dict[str, Any]) -> bool:
    meta = message.get("metadata") or {}
    if isinstance(meta, dict) and meta.get("type") == SOUL_MESSAGE_TYPE:
        return True
    content = str(message.get("content") or "")
    return message.get("role") == "system" and "## Agent Soul" in content


def strip_soul_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [m for m in messages if not is_soul_message(m)]


def inject_soul_into_messages(
    messages: list[dict[str, Any]],
    profile: str | None = None,
) -> list[dict[str, Any]]:
    rest = strip_soul_messages(messages)
    return [build_soul_message(profile)] + rest


def profile_name_from_agent(agent: Any) -> str:
    config = getattr(agent, "config", None)
    name = getattr(config, "profile_name", None) if config else None
    return (name or "default").strip() or "default"