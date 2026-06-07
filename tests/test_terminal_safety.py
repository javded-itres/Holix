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


def test_helix_in_default_whitelist():
    ok, reason = command_whitelist.is_command_allowed("helix gateway status")
    assert ok, reason


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
async def test_terminal_tool_blocks_dangerous(monkeypatch: pytest.MonkeyPatch) -> None:
    from config import settings
    from core.tools.terminal import TerminalTool

    monkeypatch.setattr(settings, "enable_terminal_tool", True)
    monkeypatch.setattr(settings, "terminal_command_whitelist", True)
    tool = TerminalTool()
    out = await tool.execute("rm -rf /tmp/test")
    assert "blocked" in out.lower() or "Error" in out