"""Inline keyboards for Telegram Helix UX."""

from __future__ import annotations

from typing import Any

PREFIX = "hx"

MODE_LABELS: dict[str, tuple[str, str]] = {
    "react": ("ReAct", "tool-вызовы по шагам"),
    "plan_and_execute": ("Plan", "план → выполнение"),
    "hybrid": ("Hybrid", "план + ReAct"),
    "auto": ("Auto", "автовыбор режима"),
}


def _cb(action: str, value: str) -> str:
    data = f"{PREFIX}:{action}:{value}"
    if len(data) > 64:
        raise ValueError(f"callback_data too long: {data!r}")
    return data


def parse_callback(data: str) -> tuple[str, str] | None:
    if not data or not data.startswith(f"{PREFIX}:"):
        return None
    parts = data.split(":", 2)
    if len(parts) != 3:
        return None
    return parts[1], parts[2]


def _mark(current: bool) -> str:
    return "✓ " if current else ""


def mode_picker_keyboard(modes: list[str], current: str) -> Any:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    rows: list[list[Any]] = []
    row: list[Any] = []
    for mode in modes:
        label = MODE_LABELS.get(mode, (mode, ""))[0]
        row.append(
            InlineKeyboardButton(
                text=f"{_mark(mode == current)}{label}",
                callback_data=_cb("m", mode),
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="↻ Обновить", callback_data=_cb("r", "mode"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def stream_picker_keyboard(enabled: bool) -> Any:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{_mark(enabled)}Стриминг Вкл",
                    callback_data=_cb("st", "1"),
                ),
                InlineKeyboardButton(
                    text=f"{_mark(not enabled)}Выкл",
                    callback_data=_cb("st", "0"),
                ),
            ],
        ]
    )


def profile_picker_keyboard(profiles: list[str], current: str) -> Any:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    rows: list[list[Any]] = []
    row: list[Any] = []
    for i, name in enumerate(profiles[:12]):
        short = name if len(name) <= 14 else name[:12] + "…"
        row.append(
            InlineKeyboardButton(
                text=f"{_mark(name == current)}{short}",
                callback_data=_cb("pi", str(i)),
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def sessions_picker_keyboard(
    sessions: list[dict],
    current_id: str,
    *,
    page: int = 0,
    page_size: int = 8,
) -> Any:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    start = page * page_size
    chunk = sessions[start : start + page_size]
    rows: list[list[Any]] = []
    for i, s in enumerate(chunk):
        cid = s.get("conversation_id", "?")
        label = s.get("title") or s.get("name") or cid
        if len(label) > 28:
            label = label[:26] + "…"
        global_idx = start + i
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{_mark(cid == current_id)}{global_idx + 1}. {label}",
                    callback_data=_cb("s", str(global_idx)),
                )
            ]
        )
    nav: list[Any] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(text="◀", callback_data=_cb("sp", str(page - 1)))
        )
    if start + page_size < len(sessions):
        nav.append(
            InlineKeyboardButton(text="▶", callback_data=_cb("sp", str(page + 1)))
        )
    if nav:
        rows.append(nav)
    rows.append(
        [InlineKeyboardButton(text="＋ Новая сессия", callback_data=_cb("sn", "1"))]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


SKILLS_PAGE_SIZE = 8


def skills_picker_keyboard(
    skills: list[str],
    *,
    page: int = 0,
    page_size: int = SKILLS_PAGE_SIZE,
) -> Any:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    start = page * page_size
    chunk = skills[start : start + page_size]
    rows: list[list[Any]] = []
    row: list[Any] = []
    for i, name in enumerate(chunk):
        global_idx = start + i
        label = name if len(name) <= 22 else name[:20] + "…"
        row.append(
            InlineKeyboardButton(
                text=label,
                callback_data=_cb("sk", str(global_idx)),
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    nav: list[Any] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(text="◀", callback_data=_cb("skp", str(page - 1)))
        )
    if start + page_size < len(skills):
        nav.append(
            InlineKeyboardButton(text="▶", callback_data=_cb("skp", str(page + 1)))
        )
    if nav:
        rows.append(nav)
    rows.append(
        [InlineKeyboardButton(text="↻ Обновить", callback_data=_cb("skp", str(page)))]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def tools_picker_keyboard(tools: list[dict]) -> Any:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    rows: list[list[Any]] = []
    recent = list(tools[-8:])
    for i, entry in enumerate(reversed(recent)):
        name = entry.get("name", "tool")
        if len(name) > 24:
            name = name[:22] + "…"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{i + 1}. {name}",
                    callback_data=_cb("t", str(i)),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _model_button_label(model_id: str, *, active: bool, max_len: int = 28) -> str:
    short = model_id if len(model_id) <= max_len else model_id[: max_len - 1] + "…"
    return f"{_mark(active)}{short}"


def models_root_keyboard(
    presets: list,
    providers: list,
    active_slot: str,
    *,
    provider_page: int = 0,
    page_size: int = 8,
) -> Any:
    """Root: presets + provider buttons."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    rows: list[list[Any]] = []

    if presets:
        row: list[Any] = []
        for i, choice in enumerate(presets):
            label = getattr(choice, "label", "preset")
            short = label if len(label) <= 14 else label[:12] + "…"
            row.append(
                InlineKeyboardButton(
                    text=f"{_mark(getattr(choice, 'slot_id', '') == active_slot)}{short}",
                    callback_data=_cb("mp", str(i)),
                )
            )
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)

    start = provider_page * page_size
    chunk = providers[start : start + page_size]
    row = []
    for i, prov in enumerate(chunk):
        global_idx = start + i
        name = getattr(prov, "name", str(prov))
        count = len(getattr(prov, "models", ()))
        short = name if len(name) <= 12 else name[:10] + "…"
        row.append(
            InlineKeyboardButton(
                text=f"📡 {short} ({count})",
                callback_data=_cb("mg", str(global_idx)),
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    nav: list[Any] = []
    if provider_page > 0:
        nav.append(
            InlineKeyboardButton(text="◀ Пров.", callback_data=_cb("mgp", str(provider_page - 1)))
        )
    if start + page_size < len(providers):
        nav.append(
            InlineKeyboardButton(text="Пров. ▶", callback_data=_cb("mgp", str(provider_page + 1)))
        )
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="↻ Обновить", callback_data=_cb("r", "models"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def models_provider_keyboard(
    provider_name: str,
    models: list[str],
    active_slot: str,
    provider_idx: int,
    *,
    page: int = 0,
    page_size: int = 10,
) -> Any:
    """Models of one provider (no prefix in labels) + pagination."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    start = page * page_size
    chunk = models[start : start + page_size]
    rows: list[list[Any]] = []
    row: list[Any] = []
    for i, model_id in enumerate(chunk):
        global_idx = start + i
        slot = f"prov:{provider_name}:{model_id}"
        row.append(
            InlineKeyboardButton(
                text=_model_button_label(model_id, active=slot == active_slot),
                callback_data=_cb("mm", f"{provider_idx}:{global_idx}"),
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    nav: list[Any] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀", callback_data=_cb("mv", f"{provider_idx}:{page - 1}")))
    if start + page_size < len(models):
        nav.append(InlineKeyboardButton(text="▶", callback_data=_cb("mv", f"{provider_idx}:{page + 1}")))
    if nav:
        rows.append(nav)

    rows.append(
        [
            InlineKeyboardButton(text="← Провайдеры", callback_data=_cb("mb", "0")),
            InlineKeyboardButton(text="↻", callback_data=_cb("mg", str(provider_idx))),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def status_menu_keyboard(locale: str | None = None) -> Any:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from core.i18n.messages import t

    loc = locale or "en"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t("tg.menu.mode", loc), callback_data=_cb("r", "mode")),
                InlineKeyboardButton(text=t("tg.menu.profile", loc), callback_data=_cb("r", "profile")),
            ],
            [
                InlineKeyboardButton(text=t("tg.menu.sessions", loc), callback_data=_cb("r", "sessions")),
                InlineKeyboardButton(text=t("tg.menu.streaming", loc), callback_data=_cb("r", "stream")),
            ],
            [
                InlineKeyboardButton(text=t("tg.menu.models", loc), callback_data=_cb("r", "models")),
                InlineKeyboardButton(text="Tools", callback_data=_cb("r", "tools")),
            ],
            [
                InlineKeyboardButton(text=t("tg.menu.compress", loc), callback_data=_cb("r", "compress")),
            ],
            [
                InlineKeyboardButton(text="Cron", callback_data=_cb("r", "cron")),
            ],
        ]
    )


def mode_picker_html(current: str) -> str:
    lines = ["<b>Режим выполнения</b>", f"Сейчас: <code>{current}</code>", ""]
    for mode, (title, hint) in MODE_LABELS.items():
        mark = "✓ " if mode == current else ""
        lines.append(f"{mark}<b>{title}</b> (<code>{mode}</code>) — {hint}")
    lines.append("")
    lines.append("<i>Выберите кнопку ниже</i>")
    return "\n".join(lines)