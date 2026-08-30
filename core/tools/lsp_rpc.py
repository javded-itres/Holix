"""Minimal LSP JSON-RPC client over stdio (one query per spawned server)."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from core.tools.lsp_servers import ResolvedLsp


class LspProtocolError(RuntimeError):
    """Language server protocol or process failure."""


def _uri(path: Path) -> str:
    return path.expanduser().resolve().as_uri()


def _normalize_markup(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if "value" in value:
            return str(value.get("value") or "")
        if "contents" in value:
            return _normalize_markup(value.get("contents"))
        left = value.get("left")
        if isinstance(left, dict) and "value" in left:
            return str(left.get("value") or "")
    if isinstance(value, list):
        parts = [_normalize_markup(item) for item in value]
        return "\n".join(p for p in parts if p)
    return str(value)


def _as_locations(value: Any) -> list[dict[str, Any]]:
    if not value:
        return []
    items = value if isinstance(value, list) else [value]
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        target = item.get("targetUri") or item.get("uri") or ""
        rng = item.get("targetSelectionRange") or item.get("targetRange") or item.get("range") or {}
        start = rng.get("start") if isinstance(rng, dict) else {}
        out.append(
            {
                "path": str(target),
                "line": int((start or {}).get("line", 0) or 0) + 1,
                "column": int((start or {}).get("character", 0) or 0),
            }
        )
    return out


def _as_symbols(value: Any) -> list[dict[str, Any]]:
    if not value:
        return []
    items = value if isinstance(value, list) else [value]
    out: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        loc = node.get("location") if isinstance(node.get("location"), dict) else {}
        rng = node.get("range") or loc.get("range") or node.get("selectionRange") or {}
        start = rng.get("start") if isinstance(rng, dict) else {}
        out.append(
            {
                "name": str(node.get("name") or ""),
                "kind": node.get("kind"),
                "path": str(loc.get("uri") or ""),
                "line": int((start or {}).get("line", 0) or 0) + 1,
                "column": int((start or {}).get("character", 0) or 0),
            }
        )
        for child in node.get("children") or []:
            walk(child)

    for item in items:
        walk(item)
    return out[:40]


class _LspClient:
    def __init__(self, argv: list[str], cwd: Path) -> None:
        self._argv = argv
        self._cwd = cwd
        self._proc: asyncio.subprocess.Process | None = None
        self._buf = b""
        self._next_id = 0
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._diagnostics: list[dict[str, Any]] = []
        self._reader: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._proc = await asyncio.create_subprocess_exec(
            *self._argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=str(self._cwd),
            limit=8 * 1024 * 1024,
        )
        self._reader = asyncio.create_task(self._read_loop())

    async def close(self) -> None:
        proc = self._proc
        if proc is None:
            return
        try:
            if proc.returncode is None:
                try:
                    await self.notify("exit")
                except Exception:
                    pass
                proc.kill()
                await proc.wait()
        except Exception:
            pass
        if self._reader is not None:
            self._reader.cancel()
        self._proc = None

    async def notify(self, method: str, params: Any = None) -> None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        await self._send(payload)

    async def request(self, method: str, params: Any = None) -> Any:
        self._next_id += 1
        req_id = self._next_id
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        self._pending[req_id] = fut
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            payload["params"] = params
        await self._send(payload)
        return await fut

    async def _send(self, payload: dict[str, Any]) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise LspProtocolError("language server is not running")
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        proc.stdin.write(header + body)
        await proc.stdin.drain()

    async def _read_loop(self) -> None:
        try:
            while True:
                msg = await self._read_message()
                if msg is None:
                    break
                await self._dispatch(msg)
        except Exception:
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(LspProtocolError("language server closed"))
            self._pending.clear()

    async def _dispatch(self, msg: dict[str, Any]) -> None:
        if "id" in msg and "method" in msg:
            try:
                await self._send({"jsonrpc": "2.0", "id": msg["id"], "result": None})
            except Exception:
                pass
            return
        if "id" in msg:
            fut = self._pending.pop(int(msg["id"]), None)
            if fut is None or fut.done():
                return
            if "error" in msg:
                fut.set_exception(LspProtocolError(str(msg.get("error"))))
            else:
                fut.set_result(msg.get("result"))
            return
        if msg.get("method") == "textDocument/publishDiagnostics":
            params = msg.get("params") or {}
            diags = params.get("diagnostics") or []
            if isinstance(diags, list):
                self._diagnostics = [d for d in diags if isinstance(d, dict)]

    async def _read_message(self) -> dict[str, Any] | None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return None
        while True:
            sep = self._buf.find(b"\r\n\r\n")
            if sep != -1:
                header = self._buf[:sep].decode("ascii", errors="replace")
                self._buf = self._buf[sep + 4 :]
                length = 0
                for line in header.split("\r\n"):
                    if line.lower().startswith("content-length:"):
                        try:
                            length = int(line.split(":", 1)[1].strip())
                        except ValueError as exc:
                            raise LspProtocolError("invalid Content-Length") from exc
                if length <= 0:
                    continue
                while len(self._buf) < length:
                    chunk = await proc.stdout.read(length - len(self._buf))
                    if not chunk:
                        return None
                    self._buf += chunk
                body, self._buf = self._buf[:length], self._buf[length:]
                try:
                    data = json.loads(body.decode("utf-8"))
                except json.JSONDecodeError as exc:
                    raise LspProtocolError("invalid JSON from language server") from exc
                if isinstance(data, dict):
                    return data
                return None
            chunk = await proc.stdout.read(4096)
            if not chunk:
                return None
            self._buf += chunk
            if len(self._buf) > 16 * 1024 * 1024:
                raise LspProtocolError("language server header too large")


async def query_language_server(
    resolved: ResolvedLsp,
    *,
    root: Path,
    file_path: Path,
    source: str,
    action: str,
    line: int,
    character: int,
    query: str = "",
    timeout_s: float = 20.0,
) -> dict[str, Any]:
    """Run one LSP session: initialize, didOpen, request, shutdown."""
    client = _LspClient(resolved.argv, root)
    lsp_line = max(0, int(line) - 1)
    col = max(0, int(character))
    uri = _uri(file_path)
    pos = {"line": lsp_line, "character": col}
    doc = {"uri": uri}

    async def _run() -> dict[str, Any]:
        await client.start()
        await client.request(
            "initialize",
            {
                "processId": os.getpid(),
                "rootUri": _uri(root),
                "capabilities": {
                    "workspace": {"workspaceFolders": True},
                    "textDocument": {
                        "hover": {"contentFormat": ["plaintext", "markdown"]},
                        "definition": {"linkSupport": True},
                        "references": {},
                        "implementation": {},
                        "documentSymbol": {"hierarchicalDocumentSymbolSupport": True},
                        "publishDiagnostics": {},
                        "diagnostic": {},
                    },
                },
                "workspaceFolders": [{"uri": _uri(root), "name": root.name}],
            },
        )
        await client.notify("initialized", {})
        await client.notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": resolved.language_id,
                    "version": 1,
                    "text": source,
                }
            },
        )
        if action == "hover":
            raw = await client.request("textDocument/hover", {"textDocument": doc, "position": pos})
            return {"items": [{"doc": _normalize_markup(raw)[:800]}]}
        if action == "definition":
            raw = await client.request(
                "textDocument/definition", {"textDocument": doc, "position": pos}
            )
            return {"items": _as_locations(raw)}
        if action == "implementation":
            try:
                raw = await client.request(
                    "textDocument/implementation",
                    {"textDocument": doc, "position": pos},
                )
            except LspProtocolError:
                raw = await client.request(
                    "textDocument/definition", {"textDocument": doc, "position": pos}
                )
            return {"items": _as_locations(raw)}
        if action == "references":
            raw = await client.request(
                "textDocument/references",
                {
                    "textDocument": doc,
                    "position": pos,
                    "context": {"includeDeclaration": True},
                },
            )
            return {"items": _as_locations(raw)[:20]}
        if action == "symbols":
            raw = await client.request("textDocument/documentSymbol", {"textDocument": doc})
            items = _as_symbols(raw)
            needle = (query or "").strip().lower()
            if needle:
                items = [i for i in items if needle in str(i.get("name") or "").lower()]
            return {"items": items}
        if action == "diagnostics":
            try:
                raw = await client.request("textDocument/diagnostic", {"textDocument": doc})
                items = []
                if isinstance(raw, dict):
                    items = raw.get("items") or []
                if isinstance(items, list) and items:
                    return {"items": items[:40]}
            except LspProtocolError:
                pass
            await asyncio.sleep(0.4)
            return {"items": client._diagnostics[:40]}
        raise LspProtocolError(f"unsupported action {action}")

    try:
        result = await asyncio.wait_for(_run(), timeout=timeout_s)
    finally:
        await client.close()
    return result
