"""External CLI launch (tmux) — unit tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from core.external_cli.env import build_cli_env, resolve_model_for_slot
from core.external_cli.platform import launch_supported
from core.external_cli.registry import get_cli_spec
from core.external_cli.store import ExternalCliBinding, ExternalCliStore
from core.models.manager import ModelConfig


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "holix"
    home.mkdir()
    monkeypatch.setenv("HOLIX_HOME", str(home))
    return home


def test_launch_supported_on_posix() -> None:
    import sys

    if sys.platform == "win32":
        assert launch_supported() is False
    else:
        assert launch_supported() is True


def test_build_cli_env_openai_compat() -> None:
    spec = get_cli_spec("opencode")
    assert spec is not None
    model = ModelConfig(
        provider="ollama",
        model="qwen2.5-coder",
        base_url="http://127.0.0.1:11434/v1",
        api_key="ollama",
    )
    env = build_cli_env(spec, model)
    assert env["OPENAI_API_KEY"] == "ollama"
    assert env["OPENAI_BASE_URL"] == "http://127.0.0.1:11434/v1"
    assert env["OPENAI_MODEL"] == "qwen2.5-coder"


def test_build_cli_env_anthropic() -> None:
    spec = get_cli_spec("claude")
    assert spec is not None
    model = ModelConfig(
        provider="openai",
        model="claude-sonnet",
        base_url="http://proxy/v1",
        api_key="sk-test",
    )
    env = build_cli_env(spec, model)
    assert env["ANTHROPIC_API_KEY"] == "sk-test"
    assert env["ANTHROPIC_BASE_URL"] == "http://proxy/v1"


def test_resolve_model_legacy_profile() -> None:
    cfg = SimpleNamespace(
        providers={},
        default_provider=None,
        models_via_providers=False,
        model="local-model",
        base_url="http://localhost/v1",
        api_key="key",
        temperature=0.5,
        agent_models={},
    )
    model = resolve_model_for_slot(cfg, "main")
    assert model is not None
    assert model.model == "local-model"


def test_external_cli_store_roundtrip(holix_home) -> None:
    store = ExternalCliStore("default")
    binding = ExternalCliBinding(
        cli_id="claude",
        enabled=True,
        command="/usr/bin/claude",
        model_slot="coder",
        default_cwd="/tmp/proj",
    )
    store.upsert_binding(binding)
    loaded = store.get_binding("claude")
    assert loaded is not None
    assert loaded.command == "/usr/bin/claude"
    assert loaded.model_slot == "coder"


@pytest.mark.asyncio
async def test_external_cli_tool_list_empty(holix_home, monkeypatch) -> None:
    from core.tools.external_cli import ExternalCliTool

    monkeypatch.setattr("core.tools.external_cli.launch_supported", lambda: True)
    monkeypatch.setattr("core.tools.external_cli.get_profile_name", lambda: "default")
    monkeypatch.setattr(
        "cli.services.tmux_launcher.prune_dead_sessions",
        lambda _profile: [],
    )
    tool = ExternalCliTool()
    result = await tool.execute(action="list_sessions")
    assert "No active" in result


@pytest.mark.asyncio
async def test_external_cli_tool_windows_message(monkeypatch) -> None:
    from core.tools.external_cli import ExternalCliTool

    monkeypatch.setattr("core.tools.external_cli.launch_supported", lambda: False)
    tool = ExternalCliTool()
    result = await tool.execute(action="launch", cli_id="claude")
    assert "Linux and macOS" in result