"""Route sub-agent ask_user answers in Telegram / MAX without CLI syntax."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

from core.subagents.interaction import (
    SUBAGENT_REPLY_NEED_TARGET,
    get_interaction_bridge,
    try_route_subagent_reply,
)

NEED_SUBAGENT_TARGET = SUBAGENT_REPLY_NEED_TARGET


@dataclass(frozen=True)
class ReplyRoute:
    kind: str  # delivered | gone | need_target | feedback | none
    job_id: str = ""
    feedback: str = ""


def pending_questions(agent: Any) -> list[dict[str, Any]]:
    bridge = get_interaction_bridge(agent)
    if bridge is None:
        return []
    return list(bridge.list_pending_questions() or [])


def pending_job_ids(agent: Any) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for item in pending_questions(agent):
        name = str(item.get("subagent_name") or "").strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def deliver_subagent_answer(agent: Any, job_id: str, answer: str) -> bool:
    bridge = get_interaction_bridge(agent)
    if bridge is None:
        return False
    text = (answer or "").strip()
    name = (job_id or "").strip()
    if not text or not name:
        return False
    return bool(bridge.resolve_question_for_subagent(name, text))


def remember_question_message(session: Any, message_id: Any, job_id: str) -> None:
    jid = (job_id or "").strip()
    if not jid or message_id in (None, "", 0):
        return
    mapping = getattr(session, "subagent_question_message_ids", None)
    if mapping is None:
        mapping = {}
        session.subagent_question_message_ids = mapping
    mapping[message_id] = jid
    mapping[str(message_id)] = jid


def job_id_from_reply(session: Any, reply_to_message_id: Any) -> str | None:
    if reply_to_message_id in (None, "", 0):
        return None
    mapping = getattr(session, "subagent_question_message_ids", None) or {}
    job = mapping.get(reply_to_message_id)
    if job:
        return str(job)
    job = mapping.get(str(reply_to_message_id))
    return str(job) if job else None


def ensure_job_token(mapping: dict[str, str], job_id: str) -> str:
    """Stable short token for callback_data; does not wipe other jobs."""
    jid = (job_id or "").strip()
    if not jid:
        return ""
    for token, stored in mapping.items():
        if stored == jid:
            return token
    token = secrets.token_hex(4)
    mapping[token] = jid
    return token


def tokens_for_jobs(mapping: dict[str, str], job_ids: list[str]) -> dict[str, str]:
    """Return job_id → token for the given jobs."""
    out: dict[str, str] = {}
    for jid in job_ids:
        token = ensure_job_token(mapping, jid)
        if token:
            out[jid] = token
    return out


def route_messenger_text(
    agent: Any,
    session: Any,
    message: str,
    *,
    reply_to_message_id: Any = None,
) -> ReplyRoute:
    """Deliver chat text to a waiting sub-agent, or ask the UI to pick a target."""
    text = (message or "").strip()
    if not text:
        return ReplyRoute("none")

    job = job_id_from_reply(session, reply_to_message_id)
    if job:
        if deliver_subagent_answer(agent, job, text):
            session.subagent_reply_job_id = None
            session.subagent_pending_answer = None
            return ReplyRoute("delivered", job_id=job)
        return ReplyRoute("gone")

    target = str(getattr(session, "subagent_reply_job_id", None) or "").strip()
    if target:
        if deliver_subagent_answer(agent, target, text):
            session.subagent_reply_job_id = None
            session.subagent_pending_answer = None
            return ReplyRoute("delivered", job_id=target)
        session.subagent_reply_job_id = None

    if agent is None:
        return ReplyRoute("none")

    handled, feedback = try_route_subagent_reply(agent, text)
    if not handled:
        return ReplyRoute("none")
    if feedback == NEED_SUBAGENT_TARGET:
        session.subagent_pending_answer = text
        return ReplyRoute("need_target")
    if feedback.startswith("reply sent to "):
        name = feedback[len("reply sent to ") :].strip()
        session.subagent_reply_job_id = None
        session.subagent_pending_answer = None
        return ReplyRoute("delivered", job_id=name)
    return ReplyRoute("feedback", feedback=feedback or "")


def apply_reply_button(agent: Any, session: Any, job_id: str) -> ReplyRoute:
    """Handle the Reply-to-{job} button: deliver stored text or arm the next message."""
    jid = (job_id or "").strip()
    if not jid:
        return ReplyRoute("gone")
    pending = str(getattr(session, "subagent_pending_answer", None) or "").strip()
    if pending:
        session.subagent_pending_answer = None
        session.subagent_reply_job_id = None
        if deliver_subagent_answer(agent, jid, pending):
            return ReplyRoute("delivered", job_id=jid)
        return ReplyRoute("gone")
    session.subagent_reply_job_id = jid
    return ReplyRoute("awaiting", job_id=jid)
