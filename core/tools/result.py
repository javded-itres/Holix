"""JSON tool results — never raise into the model loop."""

from __future__ import annotations

import json
from typing import Any


def tool_ok(**fields: Any) -> str:
    payload: dict[str, Any] = {"ok": True, **fields}
    return json.dumps(payload, ensure_ascii=False)


def tool_err(code: str, error: str, **fields: Any) -> str:
    payload: dict[str, Any] = {"ok": False, "code": code, "error": error, **fields}
    return json.dumps(payload, ensure_ascii=False)
