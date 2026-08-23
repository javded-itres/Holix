"""Live tail of a background process log for Telegram / MAX."""

from __future__ import annotations

import html as html_lib
from typing import Any

from core.runtime.background_process import BackgroundProcessRecord, get_background_process_registry
from core.runtime.background_process_health import tail_log_file

WATCH_INTERVAL_S = 5.0
WATCH_LINES = 28
WATCH_MAX_CHARS = 2800


def load_process_record(process_id: str) -> BackgroundProcessRecord | None:
    pid = (process_id or "").strip()
    if not pid:
        return None
    return get_background_process_registry().get(pid)


def process_log_tail(rec: BackgroundProcessRecord | None) -> str:
    if rec is None or not rec.log_path:
        return ""
    return tail_log_file(rec.log_path, max_lines=WATCH_LINES).strip()


def format_process_log_watch(
    rec: BackgroundProcessRecord | None,
    *,
    html: bool,
    locale: str = "ru",
) -> str:
    from core.i18n.messages import t

    loc = locale if locale in ("en", "ru") else "ru"
    if rec is None:
        text = t("tg.process.watch_gone", loc)
        return f"<i>{_esc(text) if html else text}</i>" if html else text

    running = rec.is_running()
    status = t(
        "tui.process.status_running" if running else "tui.process.status_stopped",
        loc,
    )
    title = t(
        "tg.process.watch_title",
        loc,
        label=rec.label or rec.process_id,
        status=status,
        pid=rec.pid,
    )
    tail = process_log_tail(rec)
    empty = not tail
    if empty:
        body = t(
            "tui.process.output_waiting" if running else "tui.process.output_empty",
            loc,
        )
    else:
        if len(tail) > WATCH_MAX_CHARS:
            tail = "…" + tail[-WATCH_MAX_CHARS:]
        body = tail

    if html:
        title_h = f"<b>{_esc(title)}</b>"
        if empty:
            return f"{title_h}\n<i>{_esc(body)}</i>"
        return f"{title_h}\n<pre>{_esc(body)}</pre>"
    return f"{title}\n{body}"


def cancel_process_log_watch(session: Any) -> None:
    task = getattr(session, "process_log_watch_task", None)
    if task is not None:
        try:
            if not task.done():
                task.cancel()
        except Exception:
            pass
    session.process_log_watch_task = None
    session.process_log_watch_id = None
    session.process_log_watch_message_id = None


def _esc(text: str) -> str:
    return html_lib.escape(text or "", quote=False)
