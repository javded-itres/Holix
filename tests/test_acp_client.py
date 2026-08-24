"""ACP client against a fake stdio agent."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from core.acp.client import AcpError, run_acp_prompt
from core.acp.config import acp_argv
from core.tools.acp import RunAcpAgentTool

_FAKE_AGENT = r"""
import json
import sys

def write(msg):
    body = json.dumps(msg).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
    sys.stdout.buffer.flush()

def read():
    headers = b""
    while b"\r\n\r\n" not in headers:
        chunk = sys.stdin.buffer.read(1)
        if not chunk:
            return None
        headers += chunk
    raw_headers, rest = headers.split(b"\r\n\r\n", 1)
    length = 0
    for line in raw_headers.split(b"\n"):
        if line.lower().startswith(b"content-length:"):
            length = int(line.split(b":", 1)[1].strip())
    body = rest
    while len(body) < length:
        more = sys.stdin.buffer.read(length - len(body))
        if not more:
            break
        body += more
    return json.loads(body[:length].decode("utf-8"))

while True:
    msg = read()
    if msg is None:
        break
    method = msg.get("method")
    req_id = msg.get("id")
    if method == "initialize":
        write({"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": 1, "agentCapabilities": {}}})
    elif method == "session/new":
        write({"jsonrpc": "2.0", "id": req_id, "result": {"sessionId": "sess_test"}})
    elif method == "session/prompt":
        prompt = msg.get("params", {}).get("prompt", [])
        text = prompt[0]["text"] if prompt else ""
        write({
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "sessionId": "sess_test",
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": "echo:" + text},
                },
            },
        })
        write({"jsonrpc": "2.0", "id": req_id, "result": {"stopReason": "end_turn"}})
    else:
        write({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": method}})
"""


@pytest.fixture
def fake_agent(tmp_path: Path) -> Path:
    path = tmp_path / "acp_echo.py"
    path.write_text(_FAKE_AGENT, encoding="utf-8")
    return path


def test_acp_argv_parses_command_and_args(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLIX_ACP_COMMAND", "grok --acp")
    monkeypatch.setenv("HOLIX_ACP_ARGS", "--verbose")
    assert acp_argv() == ["grok", "--acp", "--verbose"]
    monkeypatch.delenv("HOLIX_ACP_COMMAND")
    monkeypatch.delenv("HOLIX_ACP_ARGS")
    assert acp_argv() is None


@pytest.mark.asyncio
async def test_run_acp_prompt_echo(fake_agent: Path) -> None:
    result = await run_acp_prompt(
        "hello world",
        command=f"{sys.executable} {fake_agent}",
        timeout=15.0,
    )
    assert result.session_id == "sess_test"
    assert result.stop_reason == "end_turn"
    assert "echo:hello world" in result.text


@pytest.mark.asyncio
async def test_run_acp_agent_tool(fake_agent: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLIX_ACP_COMMAND", f"{sys.executable} {fake_agent}")
    out = await RunAcpAgentTool().execute(prompt="ping")
    assert "ACP stop=end_turn" in out
    assert "echo:ping" in out


@pytest.mark.asyncio
async def test_run_acp_agent_tool_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOLIX_ACP_COMMAND", raising=False)
    monkeypatch.delenv("HOLIX_ACP_ARGS", raising=False)
    out = await RunAcpAgentTool().execute(prompt="x")
    assert out.startswith("Error:")
    assert "HOLIX_ACP_COMMAND" in out


@pytest.mark.asyncio
async def test_missing_binary_raises() -> None:
    with pytest.raises(AcpError, match="not found"):
        await run_acp_prompt("x", command="holix-acp-agent-does-not-exist-xyz", timeout=5.0)
