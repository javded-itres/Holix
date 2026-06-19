"""Render LiveTranscriptBuffer for MAX messages."""

from __future__ import annotations

from core.i18n.live_ui import live_answer_sent_label, live_thinking_label, live_working_label
from core.presenters.live_buffer import LiveTranscriptBuffer

from integrations.max.markdown import (
    escape_html,
    markdown_to_max_html,
    truncate_max_html,
    truncate_max_text,
)


def buffer_to_max_html(buf: LiveTranscriptBuffer) -> str:
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
        body = markdown_to_max_html(answer)
        footer = (
            f"<i>🤖 {escape_html(buf.profile)} · {escape_html(buf.mode)} · ✓</i>"
        )
        return truncate_max_html(f"{body}\n\n{footer}")

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
        rendered = markdown_to_max_html(answer)
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

    return truncate_max_html("\n\n".join(parts))


def _format_tool_line(line: str) -> str:
    raw = line.strip()
    if not raw:
        return ""
    header = escape_html(raw.split("\n", 1)[0])
    header = header.replace("⎿", "▸", 1)
    return f"<b>{header}</b>"


def buffer_to_max_text(buf: LiveTranscriptBuffer) -> str:
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
        footer = f"\n\n_🤖 {buf.profile} · {buf.mode} · ✓_"
        return truncate_max_text(f"{answer}{footer}")

    parts: list[str] = [
        f"**🤖 Holix** · {buf.profile} · {buf.mode} · {buf.session_label}",
    ]
    if buf.thinking:
        label = live_thinking_label(buf.profile, fallback=buf.thinking)
        parts.append(f"_💭 {label}_")
    if show_tools:
        parts.extend(buf.tool_lines[:12])
    if answer and not buf.publish_answer_separately:
        parts.append(answer)
    for note in buf.notes[-3:]:
        if running or not done:
            parts.append(f"· {note}")
    if running and not answer and not buf.tool_lines:
        parts.append(f"_⏳ {live_working_label(buf.profile)}_")
    elif done:
        parts.append(f"_🤖 {buf.profile} · {buf.mode} · ✓_")
        if buf.publish_answer_separately and buf.result_posted_separately:
            parts.append(f"_{live_answer_sent_label(buf.profile)}_")
    elif buf.status == "error":
        parts.append("**✗ Error**")

    return truncate_max_text("\n\n".join(parts))


def buffer_to_max_plain(buf: LiveTranscriptBuffer) -> str:
    """Plain-text status fallback when HTML delivery fails."""
    answer = (buf.answer or "").strip()
    running = buf.status == "running"
    done = buf.status == "done"
    show_tools = bool(buf.tool_lines) and not done

    if done and answer and not show_tools and not buf.thinking and not buf.notes:
        return truncate_max_text(f"{answer}\n\n— Holix · {buf.profile} · {buf.mode}")

    parts: list[str] = [
        f"Holix · {buf.profile} · {buf.mode} · {buf.session_label}",
    ]
    if buf.thinking:
        parts.append(f"… {live_thinking_label(buf.profile, fallback=buf.thinking)}")
    if show_tools:
        parts.extend(buf.tool_lines[:8])
    if answer and not buf.publish_answer_separately:
        parts.append(answer)
    for note in buf.notes[-3:]:
        if running or not done:
            parts.append(note)
    if running and not answer and not buf.tool_lines:
        parts.append(f"⏳ {live_working_label(buf.profile)}")
    elif done and answer:
        parts.append(f"— Holix · {buf.profile} · {buf.mode}")
    elif buf.status == "error":
        parts.append("✗ Error")

    return truncate_max_text("\n\n".join(parts))