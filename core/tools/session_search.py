"""Search memory, other sessions, and trajectory snippets."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.tools.base import BaseTool
from core.tools.execution_context import get_conversation_id, get_profile_name
from core.tools.result import tool_err, tool_ok
from core.tools.session_memory import _resolve_memory


def _parse_since(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _hit_ts(mem: dict[str, Any]) -> str:
    meta = mem.get("metadata") if isinstance(mem.get("metadata"), dict) else {}
    for key in ("timestamp", "created_at", "ts"):
        val = meta.get(key) or mem.get(key)
        if val:
            return str(val)
    return ""


def _since_ok(ts: str, since: datetime | None) -> bool:
    if since is None or not ts:
        return True
    raw = ts[:10]
    try:
        return datetime.strptime(raw, "%Y-%m-%d") >= since
    except ValueError:
        return True


class SessionSearchTool(BaseTool):
    """Short snippets from memory, sessions, and traces — not full transcripts."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "session_search"
        self.description = (
            "Search this conversation, profile memory, other sessions, and "
            "trajectory traces (short snippets, not full transcripts). "
            "Use this before web_search when the answer may already be in the session."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "additionalProperties": False,
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "scope": {
                    "type": "string",
                    "enum": ["memory", "sessions", "traces", "all"],
                    "default": "all",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 8,
                },
                "since": {
                    "type": "string",
                    "description": "YYYY-MM-DD",
                },
            },
        }

    async def execute(
        self,
        query: str,
        scope: str = "all",
        limit: int = 8,
        since: str = "",
        **_: Any,
    ) -> str:
        q = (query or "").strip()
        if not q:
            return tool_err("missing_query", "query is required")
        want = str(scope or "all").strip().lower() or "all"
        if want not in {"memory", "sessions", "traces", "all"}:
            want = "all"
        limit = max(1, min(int(limit or 8), 20))
        since_dt = _parse_since(since)
        hits: list[dict[str, Any]] = []

        if want in {"memory", "sessions", "all"}:
            try:
                memory = _resolve_memory()
                results = await memory.search(q, top_k=limit, conversation_id=None)
            except Exception:
                results = []
            current = get_conversation_id()
            for mem in results or []:
                if not isinstance(mem, dict):
                    continue
                meta = mem.get("metadata") if isinstance(mem.get("metadata"), dict) else {}
                session_id = str(meta.get("conversation_id") or "")
                ts = _hit_ts(mem)
                if not _since_ok(ts, since_dt):
                    continue
                snippet = str(mem.get("content") or "").replace("\n", " ").strip()
                hits.append(
                    {
                        "source": "memory" if want != "sessions" else "sessions",
                        "session_id": session_id,
                        "timestamp": ts,
                        "snippet": snippet[:240],
                        "current": session_id == current,
                    }
                )
                if len(hits) >= limit:
                    break

        if want in {"traces", "all"} and len(hits) < limit:
            try:
                from core.runtime.trajectory import TrajectoryLog

                log = TrajectoryLog(get_profile_name() or "default")
                rows = log.search(get_conversation_id() or "default", q, limit=limit)
                for row in rows:
                    ts = str(row.get("timestamp") or "")
                    if not _since_ok(ts, since_dt):
                        continue
                    snippet = str(row.get("type") or "")
                    extra = str(row.get("name") or row.get("tool_name") or "")
                    if extra:
                        snippet = f"{snippet} {extra}".strip()
                    hits.append(
                        {
                            "source": "traces",
                            "session_id": str(row.get("conversation_id") or get_conversation_id()),
                            "timestamp": ts,
                            "snippet": snippet[:240],
                        }
                    )
                    if len(hits) >= limit:
                        break
            except Exception:
                pass

        return tool_ok(matches=hits[:limit])
