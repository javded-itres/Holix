"""Profile SOUL.md — agent identity."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from cli.core import ProfileManager
from core.context.compressor import ContextCompressor
from core.profile.soul import (
    SOUL_MD_FILENAME,
    build_soul_message,
    ensure_soul_file,
    inject_soul_into_messages,
    is_soul_message,
    load_soul_md,
    soul_path,
    strip_soul_messages,
)
from core.prompt_builder import build_system_prompt
from core.runtime.context_session import compress_session_if_needed
from core.runtime.session import prepare_session


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


def test_create_profile_writes_soul_md(holix_home) -> None:
    ProfileManager().create_profile("alice")
    path = soul_path("alice")
    assert path.is_file()
    assert "Agent Soul" in path.read_text(encoding="utf-8")
    from core.profile.init import init_pending

    assert init_pending("alice")


def test_load_soul_md_creates_default_when_missing(holix_home) -> None:
    text = load_soul_md("ghost")
    assert "Agent Soul" in text
    assert soul_path("ghost").is_file()


def test_load_soul_without_init_gets_default_template(holix_home) -> None:
    soul_path("mature").parent.mkdir(parents=True)
    soul_path("mature").write_text("", encoding="utf-8")
    text = load_soul_md("mature")
    assert "Clarity over verbosity" in text


def test_build_system_prompt_always_includes_soul(holix_home) -> None:
    ensure_soul_file("default")
    soul_path("default").write_text("# Custom Soul\nBe playful.\n", encoding="utf-8")
    prompt = build_system_prompt(
        tools_description="- **read_file**: read",
        active_skills=[],
        profile_name="default",
    )
    assert "## Agent Soul" in prompt
    assert "Be playful." in prompt
    assert SOUL_MD_FILENAME in prompt


def test_inject_soul_replaces_stale_soul_message(holix_home) -> None:
    ensure_soul_file("work")
    soul_path("work").write_text("Version A", encoding="utf-8")
    messages = inject_soul_into_messages([], "work")
    assert len(messages) == 1
    assert is_soul_message(messages[0])
    assert "Version A" in messages[0]["content"]

    soul_path("work").write_text("Version B", encoding="utf-8")
    refreshed = inject_soul_into_messages(messages, "work")
    assert refreshed[0]["content"].count("Version B") == 1
    assert "Version A" not in refreshed[0]["content"]


def test_strip_soul_keeps_other_messages() -> None:
    soul = build_soul_message("default")
    user = {"role": "user", "content": "hi"}
    assert strip_soul_messages([soul, user]) == [user]


@pytest.mark.asyncio
async def test_prepare_session_injects_soul_for_new_conversation(holix_home) -> None:
    ensure_soul_file("default")
    soul_path("default").write_text("Soul on new session", encoding="utf-8")

    agent = MagicMock()
    agent.config.profile_name = "default"
    agent.memory.get_conversation = AsyncMock(return_value=[])
    agent.memory.save_message = AsyncMock()
    agent.context_manager = None

    messages, _ = await prepare_session(agent, "hello", "conv-new")

    assert is_soul_message(messages[0])
    assert "Soul on new session" in messages[0]["content"]
    assert messages[-1] == {"role": "user", "content": "hello"}


@pytest.mark.asyncio
async def test_compress_session_reinjects_soul(holix_home) -> None:
    ensure_soul_file("default")
    soul_path("default").write_text("Persistent soul", encoding="utf-8")

    original = [{"role": "user", "content": f"m{i}"} for i in range(15)]
    compressed_payload = [
        {"role": "system", "content": "Context compressed. Summary…"},
        {"role": "user", "content": "m14"},
    ]

    cm = MagicMock()
    cm.auto_compress_if_needed = AsyncMock(return_value=(compressed_payload, True))

    agent = MagicMock()
    agent.config.profile_name = "default"
    agent.context_manager = cm
    agent.memory.replace_conversation_messages = AsyncMock(return_value=2)

    result, was_compressed = await compress_session_if_needed(agent, "c1", original)

    assert was_compressed is True
    assert is_soul_message(result[0])
    assert "Persistent soul" in result[0]["content"]
    assert result[1]["content"].startswith("Context compressed")


@pytest.mark.asyncio
async def test_compressor_excludes_soul_from_summarized_chunk(holix_home) -> None:
    ensure_soul_file("default")
    counter = MagicMock()
    counter.count_message_tokens.return_value = 10
    compressor = ContextCompressor(client=MagicMock(), model="test", token_counter=counter)

    soul = build_soul_message("default")
    messages = [soul] + [{"role": "user", "content": f"x{i}"} for i in range(2)]

    compressed, summary = await compressor.compress(messages, keep_recent=3)

    assert summary == ""
    assert len(compressed) == len(messages)

    messages = [soul] + [{"role": "user", "content": f"x{i}"} for i in range(12)]
    compressor._generate_summary = AsyncMock(return_value="summary")  # type: ignore[method-assign]
    compressed, summary = await compressor.compress(messages, keep_recent=3)

    assert summary == "summary"
    assert not any(is_soul_message(m) for m in compressed)
    assert compressed[0]["content"].startswith("Context compressed")