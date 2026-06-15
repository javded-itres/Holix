"""External CLI launch (tmux) — unit tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from core.external_cli.access import external_cli_launch_error
from core.external_cli.env import build_cli_env, build_launch_args, resolve_model_for_slot
from core.external_cli.platform import launch_supported
from core.external_cli.registry import get_cli_spec, resolve_cli_selection, resolve_cli_token
from core.external_cli.store import ExternalCliBinding, ExternalCliStore
from core.models.manager import ModelConfig
from core.subagents.spawn import prepare_subagent_config
from core.tools.registry import ToolRegistry


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "holix"
    home.mkdir()
    monkeypatch.setenv("HOLIX_HOME", str(home))
    return home


def test_resolve_cli_token_by_id_and_display_name() -> None:
    assert resolve_cli_token("claude") == "claude"
    assert resolve_cli_token("Claude Code") == "claude"
    assert resolve_cli_token("OpenAI Codex CLI") is None
    assert resolve_cli_token("opencode") == "opencode"
    assert resolve_cli_token("OpenCode") == "opencode"
    assert resolve_cli_token("codex-app") is None
    assert resolve_cli_token("Codex App") is None
    assert resolve_cli_token("grok-build") == "grok-build"
    assert resolve_cli_token("Grok Build") == "grok-build"
    assert resolve_cli_token("aider") == "aider"
    assert resolve_cli_token("unknown tool") is None


def test_resolve_cli_selection_mixed_input() -> None:
    ids, unknown = resolve_cli_selection("Claude Code, aider")
    assert ids == ["claude", "aider"]
    assert unknown == []

    ids2, unknown2 = resolve_cli_selection("claude, bad-name")
    assert ids2 == ["claude"]
    assert unknown2 == ["bad-name"]

    ids3, _ = resolve_cli_selection("all")
    assert "claude" in ids3
    assert "opencode" in ids3
    assert "codex" not in ids3
    assert "codex-app" not in ids3
    assert "grok-build" in ids3


def test_launch_supported_on_posix() -> None:
    import sys

    if sys.platform == "win32":
        assert launch_supported() is False
    else:
        assert launch_supported() is True


def test_build_cli_env_openai_compat() -> None:
    spec = get_cli_spec("aider")
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


def test_build_cli_env_opencode(holix_home) -> None:
    spec = get_cli_spec("opencode")
    assert spec is not None
    model = ModelConfig(
        provider="litellm",
        model="coder",
        base_url="http://proxy:4000/v1",
        api_key="sk-test",
    )
    env = build_cli_env(spec, model, profile="default")
    config_path = holix_home / "profiles" / "default" / "opencode" / "opencode.json"
    assert env["OPENCODE_CONFIG"] == str(config_path.resolve())
    assert "OPENAI_API_KEY" not in env
    config_text = config_path.read_text(encoding="utf-8")
    assert '"model": "holix/coder"' in config_text
    assert '"baseURL": "http://proxy:4000/v1"' in config_text
    assert build_launch_args(spec, model) == ("-m", "holix/coder")


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
    assert env["ANTHROPIC_BASE_URL"] == "http://proxy"
    assert env["CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY"] == "1"
    assert "ANTHROPIC_CUSTOM_MODEL_OPTION" not in env


def test_build_cli_env_anthropic_litellm_alias() -> None:
    spec = get_cli_spec("claude")
    assert spec is not None
    model = ModelConfig(
        provider="litellm",
        model="coder",
        base_url="http://192.168.1.10:4000/v1",
        api_key="sk-test",
    )
    env = build_cli_env(spec, model)
    assert env["ANTHROPIC_BASE_URL"] == "http://192.168.1.10:4000"
    assert env["ANTHROPIC_MODEL"] == "coder"
    assert env["ANTHROPIC_CUSTOM_MODEL_OPTION"] == "coder"
    assert env["CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY"] == "1"


def test_build_cli_env_grok(holix_home) -> None:
    spec = get_cli_spec("grok-build")
    assert spec is not None
    model = ModelConfig(
        provider="litellm",
        model="coder",
        base_url="http://proxy:4000/v1",
        api_key="xai-test",
    )
    env = build_cli_env(spec, model, profile="default")
    assert env["XAI_API_KEY"] == "xai-test"
    assert env["GROK_MODELS_BASE_URL"] == "http://proxy:4000/v1"
    assert "OPENAI_API_KEY" not in env
    grok_home = holix_home / "profiles" / "default" / "grok"
    assert env["GROK_HOME"] == str(grok_home.resolve())
    config_text = (grok_home / "config.toml").read_text(encoding="utf-8")
    assert "[model.coder]" in config_text
    assert 'base_url = "http://proxy:4000/v1"' in config_text
    assert build_launch_args(spec, model) == ("-m", "coder")


def test_build_launch_args_grok_task_positional() -> None:
    spec = get_cli_spec("grok-build")
    assert spec is not None
    model = ModelConfig(
        provider="litellm",
        model="coder",
        base_url="http://proxy:4000/v1",
        api_key="xai-test",
    )
    assert build_launch_args(spec, model, "fix the auth test") == (
        "-m",
        "coder",
        "fix the auth test",
    )


def test_build_cli_env_anthropic_first_party_skips_gateway() -> None:
    spec = get_cli_spec("claude")
    assert spec is not None
    model = ModelConfig(
        provider="anthropic",
        model="claude-sonnet-4-6",
        base_url="https://api.anthropic.com",
        api_key="sk-test",
    )
    env = build_cli_env(spec, model)
    assert env["ANTHROPIC_BASE_URL"] == "https://api.anthropic.com"
    assert "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY" not in env
    assert "ANTHROPIC_CUSTOM_MODEL_OPTION" not in env


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


def test_external_cli_launch_requires_assigned_subagent(holix_home) -> None:
    store = ExternalCliStore("default")
    store.upsert_binding(
        ExternalCliBinding(
            cli_id="claude",
            enabled=True,
            command="/usr/bin/claude",
            model_slot="coder",
            agent_slot="coder",
        )
    )

    assert external_cli_launch_error("default", "claude", caller_agent_type="") is not None
    assert external_cli_launch_error("default", "claude", caller_agent_type="main") is not None
    assert external_cli_launch_error("default", "claude", caller_agent_type="researcher") is not None
    assert external_cli_launch_error("default", "claude", caller_agent_type="coder") is None

    store.upsert_binding(
        ExternalCliBinding(
            cli_id="claude",
            enabled=False,
            command="/usr/bin/claude",
            agent_slot="coder",
        )
    )
    assert "disabled" in (external_cli_launch_error("default", "claude", caller_agent_type="coder") or "")


def test_prepare_subagent_config_injects_external_cli_for_assigned_subagent(
    holix_home, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "core.external_cli.platform.launch_supported",
        lambda: True,
    )
    ExternalCliStore("default").upsert_binding(
        ExternalCliBinding(
            cli_id="claude",
            enabled=True,
            command="/usr/bin/claude",
            agent_slot="coder",
        )
    )
    parent = SimpleNamespace(
        subagent_default_process_mode="async",
        subagent_process_timeout=None,
        profile_name="default",
    )
    cfg = prepare_subagent_config("coder", parent, instance_name="coder")
    assert "external_cli" in cfg.tools
    assert cfg.agent_type == "coder"

    researcher = prepare_subagent_config("researcher", parent, instance_name="researcher")
    assert "external_cli" not in researcher.tools


@pytest.mark.asyncio
async def test_external_cli_tool_launch_blocked_for_main_agent(holix_home, monkeypatch) -> None:
    from core.tools.external_cli import ExternalCliTool

    ExternalCliStore("default").upsert_binding(
        ExternalCliBinding(
            cli_id="claude",
            enabled=True,
            command="/usr/bin/claude",
            agent_slot="coder",
        )
    )
    monkeypatch.setattr("core.tools.external_cli.launch_supported", lambda: True)
    monkeypatch.setattr("core.tools.external_cli.get_profile_name", lambda: "default")
    monkeypatch.setattr("core.tools.external_cli.get_subagent_type", lambda: "")

    tool = ExternalCliTool()
    result = await tool.execute(action="launch", cli_id="claude", task="fix tests")
    assert "assigned sub-agents" in result


@pytest.mark.asyncio
async def test_external_cli_tool_launch_allowed_for_assigned_subagent(
    holix_home,
    monkeypatch,
) -> None:
    from core.tools.external_cli import ExternalCliTool

    ExternalCliStore("default").upsert_binding(
        ExternalCliBinding(
            cli_id="claude",
            enabled=True,
            command="/usr/bin/claude",
            agent_slot="coder",
        )
    )
    launched = SimpleNamespace(
        tmux_session="holix-default-claude-abc",
        session_id="sess-1",
        model_name="coder",
        cwd="/tmp",
    )

    monkeypatch.setattr("core.tools.external_cli.launch_supported", lambda: True)
    monkeypatch.setattr("core.tools.external_cli.get_profile_name", lambda: "default")
    monkeypatch.setattr("core.tools.external_cli.get_subagent_type", lambda: "coder")
    monkeypatch.setattr(
        "cli.services.tmux_launcher.launch_cli_by_id",
        lambda **kwargs: launched,
    )
    monkeypatch.setattr(
        "cli.core.get_profile_manager",
        lambda: SimpleNamespace(load_profile=lambda _p: SimpleNamespace()),
    )

    tool = ExternalCliTool()
    result = await tool.execute(action="launch", cli_id="claude", task="fix tests")
    assert "Launched claude" in result


def test_main_agent_tool_schemas_hide_external_cli() -> None:
    registry = ToolRegistry()
    registry.register_all()
    names = {schema["function"]["name"] for schema in registry.get_schemas()}
    assert "external_cli" not in names

    names_sub = {schema["function"]["name"] for schema in registry.get_schemas(for_agent_slot="coder")}
    if launch_supported():
        assert "external_cli" in names_sub