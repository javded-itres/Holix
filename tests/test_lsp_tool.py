"""Multi-language lsp tool: catalog, jedi, and stdio JSON-RPC."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from core.tools.execution_context import reset_workspace_scope, workspace_scope
from core.tools.lsp import LspTool
from core.tools.lsp_servers import (
    language_id_for,
    pyright_available,
    python_lsp_ready,
    resolve_lsp,
    status_rows,
)

_FAKE_SERVER = r"""
import json, sys

def read_msg():
    headers = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        if b":" in line:
            k, v = line.decode("ascii", errors="replace").split(":", 1)
            headers[k.strip().lower()] = v.strip()
    n = int(headers.get("content-length", "0"))
    body = sys.stdin.buffer.read(n)
    return json.loads(body.decode("utf-8"))

def send(obj):
    raw = json.dumps(obj).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw)
    sys.stdout.buffer.flush()

while True:
    msg = read_msg()
    if msg is None:
        break
    method = msg.get("method")
    mid = msg.get("id")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": mid, "result": {"capabilities": {}}})
    elif method == "initialized":
        continue
    elif method == "textDocument/didOpen":
        continue
    elif method == "textDocument/hover":
        send({"jsonrpc": "2.0", "id": mid, "result": {"contents": {"kind": "markdown", "value": "fake-hover"}}})
    elif method == "textDocument/definition":
        send({"jsonrpc": "2.0", "id": mid, "result": {"uri": "file:///tmp/x.go", "range": {"start": {"line": 2, "character": 0}}}})
    elif method == "shutdown":
        send({"jsonrpc": "2.0", "id": mid, "result": None})
    elif method == "exit":
        break
"""


def test_language_id_for_suffixes() -> None:
    assert language_id_for(Path("a.py")) == "python"
    assert language_id_for(Path("a.ts")) == "typescript"
    assert language_id_for(Path("a.go")) == "go"
    assert language_id_for(Path("Dockerfile")) == "dockerfile"
    assert language_id_for(Path("x.rs"), "rust") == "rust"


def test_status_rows_include_recommended() -> None:
    rows = status_rows()
    ids = {r["id"] for r in rows}
    assert "python-pyright" in ids
    assert "python-jedi" in ids
    assert "typescript" in ids
    assert "go" in ids
    rec = {r["id"] for r in rows if r["recommended"]}
    assert "python-pyright" in rec
    assert "python-jedi" not in rec


@pytest.mark.asyncio
async def test_lsp_status_action() -> None:
    raw = await LspTool().execute(action="status")
    payload = json.loads(raw)
    assert payload["ok"] is True
    assert "servers" in payload
    assert isinstance(payload["ready"], list)


@pytest.mark.asyncio
async def test_lsp_unavailable_unknown_language(tmp_path: Path) -> None:
    f = tmp_path / "x.unknownlang"
    f.write_text("hello\n", encoding="utf-8")
    tokens = workspace_scope(workspace_root=str(tmp_path), workspace_jail_enabled=True)
    try:
        raw = await LspTool().execute(action="hover", path="x.unknownlang", line=1, character=0)
        payload = json.loads(raw)
        assert payload["ok"] is False
        assert payload["code"] == "lsp_unavailable"
        assert payload["fallback"] == "grep"
        assert "install" in payload
    finally:
        reset_workspace_scope(tokens)


@pytest.mark.asyncio
async def test_lsp_jedi_hover_when_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("jedi")
    monkeypatch.setattr("core.tools.lsp_servers.which_argv", lambda argv: None)
    f = tmp_path / "mod.py"
    f.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    tokens = workspace_scope(workspace_root=str(tmp_path), workspace_jail_enabled=True)
    try:
        raw = await LspTool().execute(
            action="hover", path="mod.py", line=1, character=4, language="python"
        )
        payload = json.loads(raw)
        assert payload["ok"] is True
        assert payload["server"] == "python-jedi"
        assert payload["items"]
    finally:
        reset_workspace_scope(tokens)


@pytest.mark.asyncio
async def test_lsp_pyright_hover_when_installed(tmp_path: Path) -> None:
    from core.tools.lsp_servers import pyright_available

    if not pyright_available():
        pytest.skip("pyright-langserver not installed")
    f = tmp_path / "mod.py"
    f.write_text("def add(a, b):\n    return a + b\n\nx = add(1, 2)\n", encoding="utf-8")
    tokens = workspace_scope(workspace_root=str(tmp_path), workspace_jail_enabled=True)
    try:
        hover = json.loads(
            await LspTool().execute(
                action="hover", path="mod.py", line=1, character=4, language="python"
            )
        )
        assert hover["ok"] is True, hover
        assert hover["server"] in {"python-pyright", "python-basedpyright"}
        defined = json.loads(
            await LspTool().execute(
                action="definition", path="mod.py", line=4, character=5, language="python"
            )
        )
        assert defined["ok"] is True, defined
        assert defined["items"], defined
    finally:
        reset_workspace_scope(tokens)


@pytest.mark.asyncio
async def test_lsp_stdio_fake_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from core.tools import lsp_servers
    from core.tools.lsp_servers import LspServerSpec, ResolvedLsp

    script = tmp_path / "fake_lsp.py"
    script.write_text(_FAKE_SERVER, encoding="utf-8")
    go = tmp_path / "main.go"
    go.write_text("package main\nfunc main() {}\n", encoding="utf-8")

    import sys

    fake = LspServerSpec(
        id="go",
        title="Go",
        suffixes=(".go",),
        language_ids=("go",),
        argv=(sys.executable, str(script)),
        recommended=False,
    )

    def _resolve(path: Path, language: str = "") -> ResolvedLsp | None:
        if path.suffix == ".go":
            return ResolvedLsp(
                spec=fake,
                argv=[sys.executable, str(script)],
                language_id="go",
                kind="lsp",
            )
        return None

    monkeypatch.setattr("core.tools.lsp.resolve_lsp", _resolve)
    monkeypatch.setattr(lsp_servers, "resolve_lsp", _resolve)
    tokens = workspace_scope(workspace_root=str(tmp_path), workspace_jail_enabled=True)
    try:
        raw = await LspTool().execute(action="hover", path="main.go", line=1, character=0)
        payload = json.loads(raw)
        assert payload["ok"] is True, payload
        assert "fake-hover" in json.dumps(payload)
        raw_def = await LspTool().execute(action="definition", path="main.go", line=1, character=0)
        defined = json.loads(raw_def)
        assert defined["ok"] is True
        assert defined["items"]
        assert defined["items"][0]["line"] == 3
    finally:
        reset_workspace_scope(tokens)


def test_resolve_python_prefers_pyright(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_which(argv):
        if argv and argv[0] == "pyright-langserver":
            return ["pyright-langserver", "--stdio"]
        return None

    monkeypatch.setattr("core.tools.lsp_servers.which_argv", fake_which)
    monkeypatch.setattr("core.tools.lsp_servers.jedi_available", lambda: True)
    resolved = resolve_lsp(tmp_path / "mod.py")
    assert resolved is not None
    assert resolved.spec.id == "python-pyright"
    assert resolved.kind == "lsp"


def test_doctor_lsp_findings() -> None:
    from cli.doctor.checks import _check_lsp

    findings = _check_lsp()
    codes = {f.code for f in findings}
    assert "lsp.ready" in codes or "lsp.none_ready" in codes
    assert any(f.code.startswith("lsp.") for f in findings)
    if not python_lsp_ready():
        assert "lsp.python_missing" in codes
    elif not pyright_available():
        assert "lsp.python_fallback" in codes
