"""Optional text embeddings for similarity of strings the caller already has.

This client is not the memory or docs embedder.
"""

from __future__ import annotations

import json
import math
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from core.decision.config import ResolvedEmbeddings, embeddings_url, max_body_bytes

Poster = Callable[[str, dict[str, Any], dict[str, str], float], Awaitable[tuple[int, bytes]]]


def cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for a, b in zip(left, right):
        dot += a * b
        left_norm += a * a
        right_norm += b * b
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return dot / math.sqrt(left_norm * right_norm)


def _vectors_from_body(api: str, body: bytes) -> list[list[float]] | str:
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "Embeddings error: unexpected response."
    if not isinstance(parsed, dict):
        return "Embeddings error: unexpected response."
    rows: list[Any]
    if api == "ollama":
        rows = parsed.get("embeddings")
        if not isinstance(rows, list):
            return "Embeddings error: unexpected response."
    else:
        data = parsed.get("data")
        if not isinstance(data, list):
            return "Embeddings error: unexpected response."
        ordered = sorted(
            (item for item in data if isinstance(item, dict)),
            key=lambda item: int(item.get("index") or 0),
        )
        rows = [item.get("embedding") for item in ordered]
    vectors: list[list[float]] = []
    for row in rows:
        if not isinstance(row, list) or not row:
            return "Embeddings error: unexpected response."
        try:
            vectors.append([float(value) for value in row])
        except (TypeError, ValueError):
            return "Embeddings error: unexpected response."
    return vectors


async def _http_post(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout_s: float,
) -> tuple[int, bytes]:
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        response = await client.post(url, json=payload, headers=headers)
        return response.status_code, response.content


async def embed_texts(
    resolved: ResolvedEmbeddings,
    texts: list[str],
    *,
    post: Poster | None = None,
) -> list[list[float]] | str:
    if not resolved.enabled:
        return "Embeddings error: embeddings are off."
    cleaned = [str(text) for text in texts]
    if not cleaned or any(not text.strip() for text in cleaned):
        return "Embeddings error: texts must be non-empty strings."
    if len(cleaned) > 8:
        return "Embeddings error: at most 8 texts."
    payload: dict[str, Any] = {"model": resolved.model, "input": cleaned}
    try:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError):
        return "Embeddings error: request is not JSON."
    if len(raw) > max_body_bytes():
        return "Embeddings error: request is larger than 1 MiB."
    headers = {"Content-Type": "application/json"}
    if resolved.api_key:
        headers["Authorization"] = f"Bearer {resolved.api_key}"
    sender = post or _http_post
    try:
        status, body = await sender(
            embeddings_url(resolved.base_url, resolved.api),
            payload,
            headers,
            resolved.timeout_s,
        )
    except httpx.TimeoutException:
        return "Embeddings error: timed out."
    except httpx.HTTPError:
        return "Embeddings error: connection failed."
    except Exception:
        return "Embeddings error: connection failed."
    if status == 401:
        return "Embeddings error: unauthorized (401)."
    if status >= 400:
        return f"Embeddings error: HTTP {status}."
    parsed = _vectors_from_body(resolved.api, body)
    if isinstance(parsed, str):
        return parsed
    if len(parsed) != len(cleaned):
        return "Embeddings error: unexpected response."
    return parsed
