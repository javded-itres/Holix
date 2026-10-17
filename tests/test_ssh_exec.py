"""ssh_exec stays off the local shell and refuses raw ssh."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from core.hub.normalize import parse_skill_file
from core.skills.bundled import bundled_skills_root
from core.tools.ssh_exec import (
    SshExecTool,
    build_ssh_argv,
    clamp_ssh_timeout,
    format_ssh_exec_block,
    parse_ssh_config_hosts,
    validate_ssh_host,
)
from core.tools.terminal import raw_ssh_redirect


def test_host_must_be_one_destination() -> None:
    assert validate_ssh_host("") is not None
    assert validate_ssh_host("-oProxyCommand=x") is not None
    assert validate_ssh_host("host;rm") is not None
    assert validate_ssh_host("ai-server-local") is None
    assert validate_ssh_host("itadmin@192.168.88.77") is None
    assert validate_ssh_host("javded@ai-server-local") is None


def test_argv_keeps_the_remote_command_as_one_argument() -> None:
    argv = build_ssh_argv("ai-server-local", "python3 -")
    assert argv[0] == "ssh"
    assert "BatchMode=yes" in argv
    assert "RequestTTY=no" in argv
    assert argv[-2] == "ai-server-local"
    assert argv[-1] == "python3 -"
    assert "--" in argv


def test_timeout_defaults_to_120_and_caps_at_600() -> None:
    assert clamp_ssh_timeout(None) == 120
    assert clamp_ssh_timeout(30) == 30
    assert clamp_ssh_timeout(900) == 600


def test_ssh_config_hint_lists_aliases_not_hostnames(tmp_path: Path) -> None:
    cfg = tmp_path / "config"
    cfg.write_text(
        "Host ai-server-local\n  HostName 10.0.0.5\n  User javded\nHost *\n  User itadmin\n",
        encoding="utf-8",
    )
    aliases, default_user = parse_ssh_config_hosts(cfg.read_text(encoding="utf-8"))
    assert aliases == [("ai-server-local", "javded")]
    assert default_user == "itadmin"
    block = format_ssh_exec_block(cfg)
    assert "ssh_exec" in block
    assert "ai-server-local (user javded)" in block
    assert "itadmin" in block
    assert "10.0.0.5" not in block
    assert "holix-ssh" in block


def test_raw_ssh_is_redirected() -> None:
    message = raw_ssh_redirect("ssh -v javded@192.168.88.252 uname")
    assert message is not None
    assert "ssh_exec" in message
    assert raw_ssh_redirect("git status") is None
    assert raw_ssh_redirect("scp ./a host:b") is not None


def test_bundled_holix_ssh_skill() -> None:
    parsed = parse_skill_file(bundled_skills_root() / "holix-ssh" / "SKILL.md")
    assert parsed is not None
    assert parsed["name"] == "holix-ssh"
    assert parsed.get("required") is True
    assert "ssh_exec" in parsed["content"]
    assert "ssh -v" in parsed["content"]


@pytest.mark.asyncio
async def test_ssh_exec_sends_stdin_without_a_local_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}

    class Proc:
        def __init__(self) -> None:
            self.returncode = 0
            self.pid = 4321

        async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:
            seen["stdin"] = input
            return b"remote-ok\n", b""

        def kill(self) -> None:
            self.returncode = -9

    async def fake_exec(*argv: str, **kwargs: object) -> Proc:
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        return Proc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr("core.tools.ssh_exec.shutil.which", lambda name: "/usr/bin/ssh")
    result = await SshExecTool().execute(
        host="ai-server-local",
        command="python3 -",
        stdin="print(1)\n",
        timeout=15,
    )
    assert "remote-ok" in result
    assert seen["argv"][0] == "/usr/bin/ssh"
    assert seen["argv"][-1] == "python3 -"
    assert seen["stdin"] == b"print(1)\n"
    assert seen["kwargs"]["stdin"] is asyncio.subprocess.PIPE


@pytest.mark.asyncio
async def test_ssh_exec_blocks_a_dangerous_remote_command() -> None:
    result = await SshExecTool().execute(host="ai-server-local", command="rm -rf /")
    assert result.startswith("Error:")
    assert "blocked" in result.lower()


@pytest.mark.asyncio
async def test_ssh_exec_allows_a_remote_profile_path(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    class Proc:
        returncode = 0

        async def communicate(self, input=None):  # noqa: A002
            seen["stdin"] = input
            return b"remote-env\n", b""

        def kill(self) -> None:
            return None

    async def fake_exec(*argv, **kwargs):
        seen["argv"] = argv
        return Proc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr("core.tools.ssh_exec.shutil.which", lambda name: "/usr/bin/ssh")
    remote = "cat /data/.holix/profiles/default/.env"
    result = await SshExecTool().execute(host="plukyanov@192.168.124.15", command=remote)
    assert "Command blocked" not in result
    assert seen["argv"][-1] == remote
