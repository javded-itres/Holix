"""POST /v1/systemone. State and criteria are sent unchanged, in the caller's language."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from core.decision.config import ResolvedDecision, max_body_bytes, systemone_url

PROBE_STATE = "проверка"
PROBE_QUESTIONS: dict[str, dict[str, str]] = {
    "probe": {
        "type": "noul",
        "instructions": "Это короткое служебное сообщение",
    }
}

Poster = Callable[[str, dict[str, Any], dict[str, str], float], Awaitable[tuple[int, bytes]]]


def _state_ok(state: Any) -> bool:
    if isinstance(state, str):
        return bool(state.strip())
    if isinstance(state, dict):
        return bool(state)
    if isinstance(state, list):
        return bool(state)
    return False


def _normalize_question(question: dict[str, Any]) -> dict[str, Any]:
    out = dict(question)
    if not str(out.get("instructions") or "").strip() and str(out.get("instruction") or "").strip():
        out["instructions"] = str(out["instruction"]).strip()
    out.pop("instruction", None)
    kind = str(out.get("type") or "").strip().lower()
    if kind:
        out["type"] = kind
    return out


def validate_request(state: Any, questions: Any) -> str | None:
    """Return an error string, or None when the body is safe to send."""
    if not _state_ok(state):
        return "System One error: state must be a non-empty string, object, or list."
    if not isinstance(questions, dict) or not questions:
        return "System One error: questions must be a non-empty object."
    for qid, raw in questions.items():
        label = str(qid)
        if not isinstance(raw, dict):
            return f"System One error: question {label} must be an object."
        question = _normalize_question(raw)
        kind = str(question.get("type") or "")
        if kind == "choice":
            criteria = question.get("criteria")
            if not isinstance(criteria, dict) or not criteria:
                return f"System One error: choice {label} criteria must be an object."
        elif kind == "score":
            criteria = question.get("criteria")
            if not isinstance(criteria, list) or len(criteria) < 2:
                return f"System One error: score {label} criteria must list at least two levels."
        elif kind == "noul":
            if not str(question.get("instructions") or "").strip():
                return f"System One error: noul {label} needs instructions."
        else:
            return f"System One error: question {label} type must be choice, score, or noul."
    return None


def _payload(resolved: ResolvedDecision, state: Any, questions: dict[str, Any]) -> dict[str, Any]:
    normalized = {str(qid): _normalize_question(question) for qid, question in questions.items()}
    return {"model": resolved.model, "state": state, "questions": normalized}


def _blocking_post(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout_s: float,
) -> tuple[int, bytes]:
    with httpx.Client(timeout=timeout_s) as client:
        response = client.post(url, json=payload, headers=headers)
        return response.status_code, response.content


async def _http_post(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout_s: float,
) -> tuple[int, bytes]:
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        response = await client.post(url, json=payload, headers=headers)
        return response.status_code, response.content


def _prepare(
    resolved: ResolvedDecision,
    state: Any,
    questions: Any,
) -> str | tuple[str, dict[str, Any], dict[str, str], float]:
    if not resolved.enabled:
        return "System One error: decision model is off."
    if resolved.preset == "jev" and not resolved.api_key:
        return "System One error: DECISION_API_KEY is not set."
    error = validate_request(state, questions)
    if error:
        return error
    assert isinstance(questions, dict)
    payload = _payload(resolved, state, questions)
    try:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError):
        return "System One error: request is not JSON."
    if len(raw) > max_body_bytes():
        return "System One error: request is larger than 1 MiB."
    headers = {"Content-Type": "application/json"}
    if resolved.api_key:
        headers["Authorization"] = f"Bearer {resolved.api_key}"
    return systemone_url(resolved.base_url), payload, headers, resolved.timeout_s


def _finish(status: int, body: bytes) -> str:
    if status == 401:
        return "System One error: unauthorized (401)."
    if status >= 400:
        return f"System One error: HTTP {status}."
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "System One error: unexpected response."
    if not isinstance(parsed, dict):
        return "System One error: unexpected response."
    return json.dumps(parsed, ensure_ascii=False)


def _transport_error(exc: Exception) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "System One error: timed out."
    return "System One error: connection failed."


async def call_systemone(
    resolved: ResolvedDecision,
    state: Any,
    questions: Any,
    *,
    post: Poster | None = None,
) -> str:
    """Return the JSON response, or a short error. Never raises for HTTP failures."""
    prepared = _prepare(resolved, state, questions)
    if isinstance(prepared, str):
        return prepared
    url, payload, headers, timeout_s = prepared
    sender = post or _http_post
    try:
        status, body = await sender(url, payload, headers, timeout_s)
    except Exception as exc:
        return _transport_error(exc)
    return _finish(status, body)


def call_systemone_blocking(
    resolved: ResolvedDecision,
    state: Any,
    questions: Any,
    *,
    post: Callable[[str, dict[str, Any], dict[str, str], float], tuple[int, bytes]] | None = None,
) -> str:
    """Sync call for code that already runs inside the agent event loop."""
    prepared = _prepare(resolved, state, questions)
    if isinstance(prepared, str):
        return prepared
    url, payload, headers, timeout_s = prepared
    sender = post or _blocking_post
    try:
        status, body = sender(url, payload, headers, timeout_s)
    except Exception as exc:
        return _transport_error(exc)
    return _finish(status, body)


async def probe_decision(resolved: ResolvedDecision, *, post: Poster | None = None) -> str:
    """One short noul in Russian. The result is ``ok`` or an error, not the state."""
    text = await call_systemone(resolved, PROBE_STATE, PROBE_QUESTIONS, post=post)
    if text.startswith("System One error:"):
        return text
    return "ok"
