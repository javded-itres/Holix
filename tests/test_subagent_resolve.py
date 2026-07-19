"""Resolve bare builtin types to specialized custom agents when unique."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.subagents.from_description import build_custom_type_from_brief
from core.subagents.resolve import resolve_subagent_type
from core.subagents.store import SubAgentTypeStore


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "holix"
    home.mkdir()
    monkeypatch.setenv("HOLIX_HOME", str(home))
    return home


def test_coder_maps_to_single_custom_specialisation(holix_home: Path) -> None:
    store = SubAgentTypeStore("default")
    custom = build_custom_type_from_brief(
        "Senior Python developer using DI and Dishka",
        name="coder-python",
        existing_names=["coder", "researcher"],
    )
    store.upsert(custom)
    assert resolve_subagent_type("coder", profile="default") == "coder-python"
    assert resolve_subagent_type("coder-python", profile="default") == "coder-python"


def test_exact_custom_unchanged(holix_home: Path) -> None:
    store = SubAgentTypeStore("default")
    custom = build_custom_type_from_brief(
        "API specialist for FastAPI services",
        name="api-dev",
        existing_names=[],
    )
    store.upsert(custom)
    assert resolve_subagent_type("api-dev", profile="default") == "api-dev"


def test_unknown_raises(holix_home: Path) -> None:
    with pytest.raises(KeyError, match="No sub-agent"):
        resolve_subagent_type("does-not-exist-xyz", profile="default")
