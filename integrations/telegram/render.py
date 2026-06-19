"""Render LiveTranscriptBuffer for Telegram messages."""

from __future__ import annotations

from core.i18n.live_ui import live_answer_sent_label, live_thinking_label, live_working_label
from core.presenters.live_buffer import LiveTranscriptBuffer

from integrations.telegram.markdown import (
    escape_html,
    markdown_to_telegram_html,
    truncate_telegram_html,
)

_TELEGRAM_MAX_LEN = 4090


def buffer_to_telegram_html(buf: LiveTranscriptBuffer) -> str:
    """Structured live/final message: tools while running, answer always as HTML."""
    answer = (buf.answer or "").strip()
    running = buf.status == "running"
    done = buf.status == "done"
    show_tools = bool(buf.tool_lines) and not done

    if (
        done
        and answer
        and not buf.publish_answer_separately
        and not show_tools
        and not buf.thinking
        and not buf.notes
    ):
        body = markdown_to_telegram_html(answer)
        footer = (
            f"<i>🤖 {escape_html(buf.profile)} · {escape_html(buf.mode)} · ✓</i>"
        )
        return truncate_telegram_html(f"{body}\n\n{footer}")

    parts: list[str] = [
        (
            f"<b>🤖 Holix</b> · {escape_html(buf.profile)} · "
            f"{escape_html(buf.mode)} · {escape_html(buf.session_label)}"
        ),
    ]

    if buf.background_process:
        icon = "🟢" if buf.background_process_healthy else "🔴"
        parts.append(
            f"<b>{icon} Process:</b> {escape_html(buf.background_process)}"
        )

    if buf.thinking:
        label = live_thinking_label(buf.profile, fallback=buf.thinking)
        parts.append(f"<i>💭 {escape_html(label)}</i>")

    if show_tools:
        tool_html: list[str] = []
        for line in buf.tool_lines:
            tool_html.append(_format_tool_line(line))
        parts.append("\n".join(tool_html))

    if answer and not buf.publish_answer_separately:
        rendered = markdown_to_telegram_html(answer)
        parts.append(rendered if rendered else escape_html(answer))

    for note in buf.notes[-3:]:
        if running or not done:
            parts.append(f"<i>· {escape_html(note)}</i>")

    if running and not answer and not buf.tool_lines:
        parts.append(f"<i>⏳ {escape_html(live_working_label(buf.profile))}</i>")
    elif done:
        parts.append(
            f"<i>🤖 {escape_html(buf.profile)} · {escape_html(buf.mode)} · ✓</i>"
        )
        if buf.publish_answer_separately and buf.result_posted_separately:
            parts.append(
                f"<i>{escape_html(live_answer_sent_label(buf.profile))}</i>"
            )
    elif buf.status == "error":
        parts.append("<b>✗ Error</b>")

    return truncate_telegram_html("\n\n".join(parts))


def _format_tool_line(line: str) -> str:
    """Tool call line — header only (no result/args body in live message)."""
    raw = line.strip()
    if not raw:
        return ""
    header = escape_html(raw.split("\n", 1)[0])
    header = header.replace("⎿", "▸", 1)
    return f"<b>{header}</b>"