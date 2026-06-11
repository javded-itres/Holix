"""First-run agent initialization — ``INIT.md`` marker per profile."""

from __future__ import annotations

from pathlib import Path

from core.env_loader import profile_dir_path

INIT_MD_FILENAME = "INIT.md"

INIT_ONBOARDING_PROMPT = """
## First-time initialization (INIT.md is active)

This Helix profile has **not** completed onboarding. Before normal task work:

1. **Introduce yourself** warmly as this user's Helix agent for this profile.
2. **Learn the user:** ask their name and how they prefer to be addressed.
3. **Learn how to work together:** pace, detail level, language, feedback style.
4. **Define your personality:** invite the user to describe the agent they want (tone, values, style).
5. **Persist as you go:**
   - User facts → `save_user_profile` (name, work_style, notes, …)
   - Agent personality / soul / identity → `save_agent_soul`
6. When the user says to **save personality, soul, identity, character, душу, личность** or similar — call `save_agent_soul` immediately with what they described.
7. When you have the user's name, work preferences, and a defined agent soul, call `complete_agent_initialization`.

Rules:
- Do **not** delete INIT.md with `write_file` — only `complete_agent_initialization`.
- Keep onboarding conversational; do not dump all questions at once unless the user prefers it.
- Match the user's language (Russian/English).
""".strip()

DEFAULT_INIT_MD = """# Initialization in progress

First-time setup for this Helix profile.
Complete onboarding with the user, then call `complete_agent_initialization`.
"""


def init_path(profile: str | None = None) -> Path:
    name = (profile or "default").strip() or "default"
    return profile_dir_path(name) / INIT_MD_FILENAME


def init_pending(profile: str | None = None) -> bool:
    return init_path(profile).is_file()


def ensure_init_file(profile: str | None = None) -> Path:
    path = init_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_text(DEFAULT_INIT_MD.strip() + "\n", encoding="utf-8")
    return path


def complete_init(profile: str | None = None) -> bool:
    path = init_path(profile)
    if not path.is_file():
        return False
    try:
        path.unlink()
    except OSError:
        return False
    return True


def format_init_block(profile: str | None = None) -> str:
    if not init_pending(profile):
        return ""
    return INIT_ONBOARDING_PROMPT