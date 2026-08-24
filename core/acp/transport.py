"""JSON-RPC 2.0 framing: LSP Content-Length, with NDJSON fallback."""

from __future__ import annotations

import json
from typing import Any


def encode_message(payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    return header + body


async def read_message(stream: Any) -> dict[str, Any] | None:
    """Read one JSON-RPC message from an asyncio StreamReader."""
    peek = await stream.read(1)
    if not peek:
        return None
    if peek == b"{":
        line = peek + await stream.readline()
        return json.loads(line.decode("utf-8"))
    header = peek
    while b"\r\n\r\n" not in header and b"\n\n" not in header:
        chunk = await stream.read(1)
        if not chunk:
            return None
        header += chunk
        if len(header) > 65_536:
            raise ValueError("ACP header too large")
    if b"\r\n\r\n" in header:
        raw_headers, rest = header.split(b"\r\n\r\n", 1)
    else:
        raw_headers, rest = header.split(b"\n\n", 1)
    length = 0
    for line in raw_headers.split(b"\n"):
        key, _, value = line.decode("ascii", errors="replace").partition(":")
        if key.strip().lower() == "content-length":
            length = int(value.strip())
            break
    if length <= 0:
        raise ValueError("ACP Content-Length missing")
    body = rest
    while len(body) < length:
        more = await stream.read(length - len(body))
        if not more:
            raise ValueError("ACP body truncated")
        body += more
    return json.loads(body[:length].decode("utf-8"))
