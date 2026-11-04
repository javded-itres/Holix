"""Opt-in semantic index of source blocks.

Chunks are top-level definitions (functions, classes, types). Vectors are a
local token hash, so search works offline without an embedding server.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any

_DIM = 64
_DEF = re.compile(
    r"^(?:async\s+def |def |class |function |export\s+(?:default\s+)?function |"
    r"export\s+class |type |fn |func |pub\s+fn )",
    re.MULTILINE,
)
_SKIP_DIRS = {
    ".git",
    ".holix",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    "target",
    ".next",
}
_SUFFIXES = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".rb"}
_TOKEN = re.compile(r"[a-z0-9_]+")


def code_index_enabled(*, profile: str | None = None, conversation_id: str | None = None) -> bool:
    raw = os.environ.get("HOLIX_CODE_INDEX", "").strip().lower()
    if raw in {"1", "on", "true", "yes"}:
        return True
    if raw in {"0", "off", "false", "no"}:
        return False
    try:
        from config import settings

        if bool(getattr(settings, "code_index_enabled", False)):
            return True
    except Exception:
        pass
    return _session_enabled(profile, conversation_id)


def _session_path(profile: str) -> Path | None:
    try:
        from core.profile.names import profile_dir_for_name

        return profile_dir_for_name(profile) / "data" / "code_index_sessions.json"
    except Exception:
        return None


def _session_enabled(profile: str | None, conversation_id: str | None) -> bool:
    path = _session_path(profile or "default")
    if path is None or not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    sessions = payload.get("sessions") if isinstance(payload, dict) else None
    if not isinstance(sessions, dict):
        return False
    return bool(sessions.get(conversation_id or "default"))


def set_session_enabled(profile: str, conversation_id: str, enabled: bool) -> None:
    path = _session_path(profile)
    if path is None:
        return
    payload: dict[str, Any] = {"sessions": {}}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("sessions"), dict):
                payload = loaded
        except (OSError, json.JSONDecodeError):
            payload = {"sessions": {}}
    payload.setdefault("sessions", {})
    payload["sessions"][conversation_id or "default"] = bool(enabled)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _bucket(token: str) -> int:
    digest = hashlib.md5(token.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % _DIM


def embed(text: str) -> list[float]:
    vec = [0.0] * _DIM
    for token in _TOKEN.findall((text or "").lower()):
        vec[_bucket(token)] += 1.0
    norm = math.sqrt(sum(value * value for value in vec)) or 1.0
    return [value / norm for value in vec]


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=False))


def chunk_source(text: str, *, path: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    starts = [match.start() for match in _DEF.finditer(text)]
    if not starts:
        body = "\n".join(lines[:80])
        if not body.strip():
            return []
        return [{"path": path, "line": 1, "text": body}]
    line_offsets = []
    cursor = 0
    for number, line in enumerate(lines, start=1):
        line_offsets.append((cursor, number))
        cursor += len(line) + 1

    def line_of(offset: int) -> int:
        found = 1
        for start, number in line_offsets:
            if start <= offset:
                found = number
            else:
                break
        return found

    chunks: list[dict[str, Any]] = []
    boundaries = starts + [len(text)]
    for index, start in enumerate(starts):
        end = boundaries[index + 1]
        body = text[start:end].strip()
        if len(body) > 4000:
            body = body[:4000]
        if body:
            chunks.append({"path": path, "line": line_of(start), "text": body})
    return chunks


def _index_path(profile: str, workspace: Path) -> Path:
    from core.profile.names import profile_dir_for_name

    digest = hashlib.sha1(str(workspace.resolve()).encode("utf-8")).hexdigest()[:12]
    return profile_dir_for_name(profile) / "data" / "code_index" / f"{digest}.json"


def _iter_files(workspace: Path, *, limit: int = 400):
    count = 0
    for path in workspace.rglob("*"):
        if count >= limit:
            return
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file() or path.suffix.lower() not in _SUFFIXES:
            continue
        count += 1
        yield path


def build_index(workspace: str | Path, *, profile: str = "default") -> dict[str, Any]:
    root = Path(workspace).expanduser().resolve()
    chunks: list[dict[str, Any]] = []
    for path in _iter_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        for chunk in chunk_source(text, path=rel):
            chunk["vector"] = embed(f"{rel}\n{chunk['text']}")
            chunks.append(chunk)
            if len(chunks) >= 2000:
                break
        if len(chunks) >= 2000:
            break
    payload = {"workspace": str(root), "chunks": chunks}
    dest = _index_path(profile, root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    return {"ok": True, "chunks": len(chunks), "path": str(dest)}


def search(
    workspace: str | Path,
    query: str,
    *,
    profile: str = "default",
    limit: int = 8,
) -> list[dict[str, Any]]:
    root = Path(workspace).expanduser().resolve()
    dest = _index_path(profile, root)
    if not dest.is_file():
        build_index(root, profile=profile)
    try:
        payload = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    needle = embed(query)
    scored: list[tuple[float, dict[str, Any]]] = []
    for chunk in payload.get("chunks") or []:
        if not isinstance(chunk, dict):
            continue
        vector = chunk.get("vector")
        if not isinstance(vector, list):
            continue
        score = _cosine(needle, [float(v) for v in vector])
        scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    hits = []
    for score, chunk in scored[: max(1, limit)]:
        if score <= 0:
            continue
        hits.append(
            {
                "path": chunk.get("path"),
                "line": chunk.get("line"),
                "score": round(score, 4),
                "preview": str(chunk.get("text") or "")[:400],
            }
        )
    return hits
