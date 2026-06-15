"""Sub-agent system prompts respect profile UI locale."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.i18n.locale import LocaleStore
from core.subagents.base import SubAgentConfig
from core.subagents.prompt import build_subagent_system_prompt


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "holix"
    home.mkdir()
    monkeypatch.setenv("HOLIX_HOME", str(home))
    return home


def test_subagent_prompt_ru_when_profile_locale_ru(holix_home) -> None:
    LocaleStore("default").set("ru")
    cfg = SubAgentConfig(name="writer", system_prompt="You write docs.")
    prompt = build_subagent_system_prompt(cfg, "Напиши README", profile_name="default")
    assert "## Язык" in prompt
    assert "ТОЛЬКО на русском" in prompt


def test_subagent_prompt_en_when_profile_locale_en(holix_home) -> None:
    LocaleStore("default").set("en")
    cfg = SubAgentConfig(name="coder", system_prompt="You code.")
    prompt = build_subagent_system_prompt(cfg, "Add tests", profile_name="default")
    assert "## Language" in prompt
    assert "only in English" in prompt