"""INIT.md onboarding, USER.md, and identity tools."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from cli.core import ProfileManager
from core.profile.init import complete_init, init_path, init_pending
from core.profile.soul import (
    is_soul_empty_or_placeholder,
    soul_path,
    update_soul_content,
)
from core.profile.user_profile import update_user_profile, user_path
from core.prompt_builder import build_system_prompt
from core.tools.profile_identity import (
    CompleteAgentInitializationTool,
    SaveAgentSoulTool,
    SaveUserProfileTool,
)


@pytest.fixture
def holix_home(tmp_path, monkeypatch: pytest.MonkeyPatch):
    import cli.core as cli_core

    root = tmp_path / "holix"
    profiles = root / "profiles"
    profiles.mkdir(parents=True)
    monkeypatch.setenv("HOLIX_HOME", str(root))
    monkeypatch.setattr(cli_core, "HOLIX_HOME", root)
    monkeypatch.setattr(cli_core, "PROFILES_DIR", profiles)
    return root


def test_create_profile_bootstraps_init_and_placeholder_soul(holix_home) -> None:
    ProfileManager().create_profile("nova")
    assert init_pending("nova")
    assert init_path("nova").is_file()
    assert is_soul_empty_or_placeholder("nova")
    assert "first conversation" in soul_path("nova").read_text(encoding="utf-8").lower()


def test_update_soul_writes_then_appends(holix_home) -> None:
    ProfileManager().create_profile("bob")
    action1 = update_soul_content("bob", "Friendly and concise.")
    assert action1 == "written"
    assert "Friendly" in soul_path("bob").read_text(encoding="utf-8")
    assert not is_soul_empty_or_placeholder("bob")

    action2 = update_soul_content("bob", "Uses emoji sparingly.", section="Tone")
    assert action2 == "appended"
    text = soul_path("bob").read_text(encoding="utf-8")
    assert "Tone" in text
    assert "emoji" in text


@pytest.mark.asyncio
async def test_save_agent_soul_tool(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    ProfileManager().create_profile("t1")

    class _Cfg:
        profile_name = "t1"
        enable_long_term_memory = False

    class _Facade:
        config = _Cfg()

    monkeypatch.setattr(
        "core.tools.profile_identity.get_memory_facade",
        lambda: _Facade(),
    )

    result = await SaveAgentSoulTool().execute("Calm expert assistant.")
    assert "written" in result
    assert "Calm expert" in soul_path("t1").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_save_user_profile_tool(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    ProfileManager().create_profile("t2")

    class _Cfg:
        profile_name = "t2"
        enable_long_term_memory = False

    class _Facade:
        config = _Cfg()

    monkeypatch.setattr(
        "core.tools.profile_identity.get_memory_facade",
        lambda: _Facade(),
    )

    result = await SaveUserProfileTool().execute(
        name="Ivan",
        work_style="Short answers, Russian",
    )
    assert "USER.md" in result
    assert "Ivan" in user_path("t2").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_complete_initialization_removes_init(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    ProfileManager().create_profile("t3")
    update_user_profile("t3", name="Anna")
    update_soul_content("t3", "Warm and proactive.")

    class _Cfg:
        profile_name = "t3"
        enable_long_term_memory = False

    class _Facade:
        config = _Cfg()
        episodic = AsyncMock()

    monkeypatch.setattr(
        "core.tools.profile_identity.get_memory_facade",
        lambda: _Facade(),
    )

    result = await CompleteAgentInitializationTool().execute(summary="Met Anna")
    assert "complete" in result.lower()
    assert not init_pending("t3")
    assert complete_init("t3") is False


def test_prompt_includes_init_block_when_pending(holix_home) -> None:
    ProfileManager().create_profile("onboard")
    prompt = build_system_prompt(
        tools_description="- **save_agent_soul**: save",
        active_skills=[],
        profile_name="onboard",
    )
    assert "First-time initialization" in prompt
    assert "save_agent_soul" in prompt
    assert "complete_agent_initialization" in prompt


def test_prompt_includes_user_block_after_save(holix_home) -> None:
    ProfileManager().create_profile("u1")
    update_user_profile("u1", name="Petr")
    prompt = build_system_prompt(
        tools_description="",
        active_skills=[],
        profile_name="u1",
    )
    assert "User profile" in prompt
    assert "Petr" in prompt