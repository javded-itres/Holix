"""Inline keyboards for MAX Helix UX."""

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
    return f"{PREFIX}:{action}:{value}"


def parse_callback(payload: str) -> tuple[str, str] | None:
    if not payload or not payload.startswith(f"{PREFIX}:"):
        return None
    parts = payload.split(":", 2)
    if len(parts) != 3:
        return None
    return parts[1], parts[2]


def _mark(current: bool) -> str:
    return "✓ " if current else ""


def _callback_btn(text: str, payload: str) -> dict[str, str]:
    return {"type": "callback", "text": text, "payload": payload}


def inline_keyboard(rows: list[list[dict[str, str]]]) -> dict[str, Any]:
    return {"type": "inline_keyboard", "payload": {"buttons": rows}}


def mode_picker_keyboard(modes: list[str], current: str) -> dict[str, Any]:
    rows: list[list[dict[str, str]]] = []
    row: list[dict[str, str]] = []
    for mode in modes:
        label = MODE_LABELS.get(mode, (mode, ""))[0]
        row.append(_callback_btn(f"{_mark(mode == current)}{label}", _cb("m", mode)))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([_callback_btn("↻ Обновить", _cb("r", "mode"))])
    return inline_keyboard(rows)


def stream_picker_keyboard(enabled: bool) -> dict[str, Any]:
    return inline_keyboard(
        [
            [
                _callback_btn(f"{_mark(enabled)}Стриминг Вкл", _cb("st", "1")),
                _callback_btn(f"{_mark(not enabled)}Выкл", _cb("st", "0")),
            ],
        ]
    )


def profile_picker_keyboard(profiles: list[str], current: str) -> dict[str, Any]:
    rows: list[list[dict[str, str]]] = []
    row: list[dict[str, str]] = []
    for i, name in enumerate(profiles[:12]):
        short = name if len(name) <= 14 else name[:12] + "…"
        row.append(_callback_btn(f"{_mark(name == current)}{short}", _cb("pi", str(i))))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return inline_keyboard(rows)


def sessions_picker_keyboard(
    sessions: list[dict],
    current_id: str,
    *,
    page: int = 0,
    page_size: int = 8,
) -> dict[str, Any]:
    start = page * page_size
    chunk = sessions[start : start + page_size]
    rows: list[list[dict[str, str]]] = []
    for i, s in enumerate(chunk):
        cid = s.get("conversation_id", "?")
        label = s.get("title") or s.get("name") or cid
        if len(label) > 28:
            label = label[:26] + "…"
        global_idx = start + i
        rows.append(
            [_callback_btn(f"{_mark(cid == current_id)}{global_idx + 1}. {label}", _cb("s", str(global_idx)))]
        )
    nav: list[dict[str, str]] = []
    if page > 0:
        nav.append(_callback_btn("◀", _cb("sp", str(page - 1))))
    if start + page_size < len(sessions):
        nav.append(_callback_btn("▶", _cb("sp", str(page + 1))))
    if nav:
        rows.append(nav)
    rows.append([_callback_btn("＋ Новая сессия", _cb("sn", "1"))])
    return inline_keyboard(rows)


def tools_picker_keyboard(tools: list[dict]) -> dict[str, Any]:
    rows: list[list[dict[str, str]]] = []
    recent = list(tools[-8:])
    for i, entry in enumerate(reversed(recent)):
        name = entry.get("name", "tool")
        if len(name) > 24:
            name = name[:22] + "…"
        rows.append([_callback_btn(f"{i + 1}. {name}", _cb("t", str(i)))])
    return inline_keyboard(rows)


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
) -> dict[str, Any]:
    rows: list[list[dict[str, str]]] = []
    if presets:
        row: list[dict[str, str]] = []
        for i, choice in enumerate(presets):
            label = getattr(choice, "label", "preset")
            short = label if len(label) <= 14 else label[:12] + "…"
            row.append(
                _callback_btn(
                    f"{_mark(getattr(choice, 'slot_id', '') == active_slot)}{short}",
                    _cb("mp", str(i)),
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
        row.append(_callback_btn(f"📡 {short} ({count})", _cb("mg", str(global_idx))))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    nav: list[dict[str, str]] = []
    if provider_page > 0:
        nav.append(_callback_btn("◀ Пров.", _cb("mgp", str(provider_page - 1))))
    if start + page_size < len(providers):
        nav.append(_callback_btn("Пров. ▶", _cb("mgp", str(provider_page + 1))))
    if nav:
        rows.append(nav)

    rows.append([_callback_btn("↻ Обновить", _cb("r", "models"))])
    return inline_keyboard(rows)


def models_provider_keyboard(
    provider_name: str,
    models: list[str],
    active_slot: str,
    provider_idx: int,
    *,
    page: int = 0,
    page_size: int = 10,
) -> dict[str, Any]:
    start = page * page_size
    chunk = models[start : start + page_size]
    rows: list[list[dict[str, str]]] = []
    row: list[dict[str, str]] = []
    for i, model_id in enumerate(chunk):
        global_idx = start + i
        slot = f"prov:{provider_name}:{model_id}"
        row.append(
            _callback_btn(
                _model_button_label(model_id, active=slot == active_slot),
                _cb("mm", f"{provider_idx}:{global_idx}"),
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    nav: list[dict[str, str]] = []
    if page > 0:
        nav.append(_callback_btn("◀", _cb("mv", f"{provider_idx}:{page - 1}")))
    if start + page_size < len(models):
        nav.append(_callback_btn("▶", _cb("mv", f"{provider_idx}:{page + 1}")))
    if nav:
        rows.append(nav)

    rows.append(
        [
            _callback_btn("← Провайдеры", _cb("mb", "0")),
            _callback_btn("↻", _cb("mg", str(provider_idx))),
        ]
    )
    return inline_keyboard(rows)


def status_menu_keyboard(locale: str | None = None, *, is_admin: bool = True) -> dict[str, Any]:
    from core.i18n.messages import t

    from integrations.messenger.locale import MESSENGER_DEFAULT_LOCALE

    loc = locale or MESSENGER_DEFAULT_LOCALE
    row0: list[dict[str, str]] = [
        _callback_btn(t("tg.menu.mode", loc), _cb("r", "mode")),
    ]
    if is_admin:
        row0.append(_callback_btn(t("tg.menu.profile", loc), _cb("r", "profile")))
    rows: list[list[dict[str, str]]] = [
        row0,
        [
            _callback_btn(t("tg.menu.sessions", loc), _cb("r", "sessions")),
            _callback_btn(t("tg.menu.streaming", loc), _cb("r", "stream")),
        ],
        [
            _callback_btn(t("tg.menu.models", loc), _cb("r", "models")),
            _callback_btn("Tools", _cb("r", "tools")),
        ],
        [
            _callback_btn(t("tg.menu.compress", loc), _cb("r", "compress")),
        ],
        [
            _callback_btn("Cron", _cb("r", "cron")),
        ],
    ]
    return inline_keyboard(rows)


def confirmation_keyboard(confirmation_id: str) -> dict[str, Any]:
    cid = confirmation_id
    return inline_keyboard(
        [
            [
                _callback_btn("✓ Once", f"cfm:{cid}:1"),
                _callback_btn("✓ Session", f"cfm:{cid}:2"),
            ],
            [
                _callback_btn("✓ Always", f"cfm:{cid}:3"),
                _callback_btn("✗ Deny", f"cfm:{cid}:4"),
            ],
        ]
    )


def access_request_admin_keyboard(user_id: int) -> dict[str, Any]:
    uid = str(int(user_id))
    return inline_keyboard(
        [
            [
                _callback_btn("✅ Одобрить", _cb("ara", uid)),
                _callback_btn("❌ Отклонить", _cb("arr", uid)),
            ],
            [_callback_btn("📁 Выбрать профиль", _cb("arl", uid))],
        ]
    )


def access_request_profile_keyboard(
    user_id: int,
    profiles: list[str],
    *,
    suggested: str,
) -> dict[str, Any]:
    uid = str(int(user_id))
    rows: list[list[dict[str, str]]] = []
    row: list[dict[str, str]] = []
    for i, name in enumerate(profiles[:10]):
        short = name if len(name) <= 18 else name[:16] + "…"
        row.append(_callback_btn(short, _cb("arp", f"{uid}:{i}")))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [_callback_btn(f"＋ Создать «{suggested[:14]}»", _cb("arp", f"{uid}:{len(profiles[:10])}"))]
    )
    rows.append([_callback_btn("← Назад", _cb("arb", uid))])
    return inline_keyboard(rows)


def format_access_resolved_admin_text(result: Any, *, approved: bool) -> str:
    from integrations.max.access_approval import AccessApprovalResult
    from integrations.max.markdown import escape_html

    if not isinstance(result, AccessApprovalResult):
        return "Готово."
    status = "одобрен" if approved else "отклонён"
    name = escape_html(result.user_display or "пользователь")
    lines = [f"✅ <b>Запрос {status}</b>", "", f"<b>Пользователь:</b> {name}"]
    if approved and result.holix_profile:
        lines.append(f"<b>Профиль Holix:</b> <code>{escape_html(result.holix_profile)}</code>")
    return "\n".join(lines)


def plan_review_keyboard(review_id: str) -> dict[str, Any]:
    rid = review_id
    return inline_keyboard(
        [
            [
                _callback_btn("Confirm step", f"plan:{rid}:confirm"),
                _callback_btn("Auto-run", f"plan:{rid}:auto"),
            ],
            [
                _callback_btn("Refine", f"plan:{rid}:refine"),
                _callback_btn("Reject", f"plan:{rid}:reject"),
            ],
        ]
    )


def mode_picker_text(current: str) -> str:
    lines = ["**Режим выполнения**", f"Сейчас: `{current}`", ""]
    for mode, (title, hint) in MODE_LABELS.items():
        mark = "✓ " if mode == current else ""
        lines.append(f"{mark}**{title}** (`{mode}`) — {hint}")
    lines.append("")
    lines.append("_Выберите кнопку ниже_")
    return "\n".join(lines)