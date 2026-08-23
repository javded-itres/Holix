"""Format sub-agent questions for Telegram / MAX (locale, job name, length)."""

from __future__ import annotations

from typing import Any

_QUESTION_MAX = 900
_CONTEXT_MAX = 1200
_MESSAGE_MAX = 3500


def mark_question_posted(session: Any, request_id: str) -> bool:
    """True if this request should be sent (first time). False if already posted."""
    rid = (request_id or "").strip()
    posted = getattr(session, "posted_subagent_question_ids", None)
    if posted is None:
        posted = set()
        session.posted_subagent_question_ids = posted
    if rid and rid in posted:
        return False
    if rid:
        posted.add(rid)
    return True


def _clip(text: str, limit: int) -> str:
    body = (text or "").strip()
    if len(body) <= limit:
        return body
    return body[: max(0, limit - 1)].rstrip() + "…"


def format_subagent_question_message(
    *,
    job_id: str,
    question: str,
    context: str = "",
    locale: str = "ru",
    html: bool = False,
) -> str:
    """Human-facing question: which job, what it asks, how to reply."""
    from core.i18n.messages import t

    name = (job_id or "").strip() or "sub-agent"
    title = t("tg.subagent_q.title", locale, name=name)
    hint = t("tg.subagent_q.hint", locale)
    q = _clip(question, _QUESTION_MAX)
    ctx = _clip(context, _CONTEXT_MAX)
    if html:
        from integrations.telegram.markdown import escape_html

        title_h = escape_html(title)
        q_h = escape_html(q)
        hint_h = escape_html(hint)
        text = f"<b>{title_h}</b>\n{q_h}"
        if ctx:
            text += f"\n\n<i>{escape_html(ctx)}</i>"
        text += f"\n\n<i>{hint_h}</i>"
    else:
        text = f"{title}\n{q}"
        if ctx:
            text += f"\n\n{ctx}"
        text += f"\n\n{hint}"
    if len(text) > _MESSAGE_MAX:
        text = text[: _MESSAGE_MAX - 1].rstrip() + "…"
    return text
