"""``holix acp`` speaks JSON-RPC and keeps the agent in the client workspace."""

from __future__ import annotations

import asyncio
import json
import os
import threading
from pathlib import Path
from types import SimpleNamespace

from cli.commands.acp_server import AcpAgent, _selected_option, prompt_text, serve
from core.acp.transport import encode_message


def test_prompt_text_reads_acp_blocks() -> None:
    assert prompt_text({"prompt": [{"type": "text", "text": "привет"}]}) == "привет"
    assert prompt_text({"prompt": "одна строка"}) == "одна строка"


def test_selected_option_reads_the_client_choice() -> None:
    result = {"outcome": {"outcome": "selected", "optionId": "allow_once"}}
    assert _selected_option(result) == "allow_once"


def _read_sync(stream) -> dict | None:
    peek = stream.read(1)
    if not peek:
        return None
    if peek == b"{":
        return json.loads(peek + stream.readline())
    header = peek
    while b"\r\n\r\n" not in header and b"\n\n" not in header:
        chunk = stream.read(1)
        if not chunk:
            return None
        header += chunk
    raw, rest = header.split(b"\r\n\r\n", 1)
    length = 0
    for line in raw.split(b"\n"):
        key, _, value = line.decode("ascii", errors="replace").partition(":")
        if key.strip().lower() == "content-length":
            length = int(value.strip())
    body = rest
    while len(body) < length:
        body += stream.read(length - len(body))
    return json.loads(body[:length])


def test_serve_answers_initialize_and_streams_the_reply(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "work"
    workspace.mkdir()

    async def open_session(self, params):
        os.chdir(params["cwd"])
        self.sessions["ses_test"] = str(params.get("conversationId") or "conv")
        return "ses_test"

    async def prompt(self, params):
        assert Path.cwd() == workspace
        assert prompt_text(params) == "правь файл"
        self._chunk("ses_test", "готово")
        return {"stopReason": "end_turn"}

    monkeypatch.setattr(AcpAgent, "open_session", open_session)
    monkeypatch.setattr(AcpAgent, "prompt", prompt)
    previous = Path.cwd()
    in_r, in_w = os.pipe()
    out_r, out_w = os.pipe()
    errors: list[BaseException] = []

    def run_server() -> None:
        stdin = os.fdopen(in_r, "rb", buffering=0)
        out = os.fdopen(out_w, "wb", buffering=0)
        try:
            asyncio.run(serve("studio", SimpleNamespace(), "", out, stdin=stdin))
        except BaseException as exc:  # noqa: BLE001 - surface the server failure to the test
            errors.append(exc)
        finally:
            out.close()

    thread = threading.Thread(target=run_server)
    thread.start()
    client_out = os.fdopen(out_r, "rb", buffering=0)
    try:
        os.write(
            in_w,
            encode_message(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": 1},
                }
            ),
        )
        started = _read_sync(client_out)
        assert started is not None
        assert started["result"]["agentInfo"]["name"] == "holix"
        os.write(
            in_w,
            encode_message(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "session/new",
                    "params": {"cwd": str(workspace), "conversationId": "ide_1"},
                }
            ),
        )
        created = _read_sync(client_out)
        assert created is not None
        assert created["result"]["sessionId"] == "ses_test"
        os.write(
            in_w,
            encode_message(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "session/prompt",
                    "params": {
                        "sessionId": "ses_test",
                        "prompt": [{"type": "text", "text": "правь файл"}],
                    },
                }
            ),
        )
        seen: list[dict] = []
        while True:
            message = _read_sync(client_out)
            assert message is not None
            seen.append(message)
            if message.get("id") == 3:
                break
        assert seen[0]["method"] == "session/update"
        assert seen[0]["params"]["update"]["content"]["text"] == "готово"
        assert seen[-1]["result"]["stopReason"] == "end_turn"
        raw = b"".join(encode_message(item) for item in seen)
        assert b"run" not in raw
    finally:
        os.close(in_w)
        client_out.close()
        thread.join(timeout=5)
        os.chdir(previous)
    assert not errors
    assert not thread.is_alive()
