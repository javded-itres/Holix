"""Shared Telegram/MAX UI for sub-agent types and Code mode."""

from __future__ import annotations

import logging
from typing import Any

from core.i18n import t
from core.subagents.registry import (
    get_subagent_config,
    is_builtin_subagent,
    list_available_subagents,
)
from core.subagents.store import (
    DEFAULT_CUSTOM_TOOLS,
    SUBAGENT_TOOL_CHOICES,
    SubAgentOverlayStore,
    SubAgentTypeStore,
    cleanup_custom_type_profile_bindings,
    sync_custom_type_profile_bindings,
)

from integrations.messenger.locale import messenger_host_locale
from integrations.messenger.presentation_settings import (
    clear_slot_presentation_for_host,
    presentation_for_host,
    set_presentation_for_host,
    slot_presentation_for_host,
)
from integrations.messenger.subagents_settings import is_subagents_enabled_for_host

logger = logging.getLogger(__name__)

PAGE_SIZE = 6
MODEL_PAGE_SIZE = 6
TEMPS = (0.0, 0.2, 0.3, 0.5, 0.7, 1.0)
PRESENTATIONS = ("native", "code", "both")
# Callback actions owned by this menu. Must not collide with sessions (`sp`), etc.
TYPE_ACTIONS = frozenset(
    {
        "tp",
        "sl",
        "sd",
        "sc",
        "sg",
        "su",
        "cm",
        "sm",
        "sx",
        "sz",
        "sb",
        "swp",
        "ds",
        "tv",
        "tt",
        "ml",
    }
)
_COMPOSE_CANCEL = frozenset({"/cancel", "cancel", "/отмена", "отмена"})
_INHERIT_SLOTS = frozenset({"", "main", "default", "inherit", "parent"})


def _profile(host: Any) -> str:
    return str(getattr(host, "profile", None) or "default")


def _session(host: Any) -> Any:
    return getattr(host, "_session", None)


def _lang(host: Any) -> str:
    return messenger_host_locale(host)


def _names(host: Any) -> list[str]:
    session = _session(host)
    names = list(getattr(session, "ui_subagent_types", None) or [])
    if names:
        return names
    return [str(i.get("name") or "") for i in list_available_subagents(profile=_profile(host))]


def _refresh_names(host: Any) -> list[str]:
    names = [str(i.get("name") or "") for i in list_available_subagents(profile=_profile(host))]
    session = _session(host)
    if session is not None:
        session.ui_subagent_types = names
    return names


def is_type_detail_view(host: Any) -> bool:
    return bool(_current_type(host)) and not is_tools_view(host)


def is_tools_view(host: Any) -> bool:
    session = _session(host)
    return bool(_current_type(host) and getattr(session, "ui_subagent_tools_view", False))


def _current_type(host: Any) -> str:
    session = _session(host)
    return str(getattr(session, "ui_subagent_current", "") or "").strip().lower()


def _set_current(host: Any, name: str) -> None:
    session = _session(host)
    if session is not None:
        session.ui_subagent_current = (name or "").strip().lower()
        session.ui_subagent_tools_view = False
        session.ui_subagent_model_page = 0
        session.ui_subagent_confirm = ""


def _set_pending(host: Any, kind: str | None) -> None:
    session = _session(host)
    if session is not None:
        session.pending_subagent_compose = kind


def _pending(host: Any) -> str | None:
    session = _session(host)
    raw = getattr(session, "pending_subagent_compose", None)
    return str(raw).strip() if raw else None


def _set_tools_view(host: Any, on: bool) -> None:
    session = _session(host)
    if session is not None:
        session.ui_subagent_tools_view = bool(on)
        session.ui_subagent_confirm = ""


def _set_confirm(host: Any, kind: str) -> None:
    session = _session(host)
    if session is not None:
        session.ui_subagent_confirm = kind


def _confirm(host: Any) -> str:
    session = _session(host)
    return str(getattr(session, "ui_subagent_confirm", "") or "")


def _type_meta(host: Any, name: str) -> dict[str, Any]:
    profile = _profile(host)
    overlay = SubAgentOverlayStore(profile).get(name)
    custom = SubAgentTypeStore(profile).get(name)
    try:
        cfg = get_subagent_config(name, profile=profile)
    except KeyError:
        cfg = None
    model_slot = (overlay.model_slot if overlay and overlay.model_slot else "") or (
        custom.model_slot if custom else ""
    )
    presentation = (
        (overlay.tools_presentation if overlay and overlay.tools_presentation else "")
        or (custom.tools_presentation if custom else "")
        or slot_presentation_for_host(host, name)
    )
    return {
        "name": name,
        "builtin": is_builtin_subagent(name),
        "description": (cfg.description if cfg else "")
        or (custom.description if custom else "")
        or "",
        "temperature": cfg.temperature
        if cfg is not None
        else (custom.temperature if custom else 0.3),
        "system_prompt": (cfg.system_prompt if cfg else "")
        or (custom.system_prompt if custom else "")
        or "",
        "tools": list(cfg.tools)
        if cfg is not None
        else list(custom.tools if custom else DEFAULT_CUSTOM_TOOLS),
        "model_slot": model_slot,
        "tools_presentation": presentation or "native",
    }


def format_list_text(host: Any) -> str:
    lang = _lang(host)
    on = is_subagents_enabled_for_host(host)
    state = "on" if on else "off"
    pres = presentation_for_host(host)
    names = _refresh_names(host)
    session = _session(host)
    page = int(getattr(session, "ui_subagent_page", 0) or 0)
    start = page * PAGE_SIZE
    chunk = names[start : start + PAGE_SIZE]
    lines = [
        f"<b>{_esc(t('tg.subagents_picker_title', lang))}</b>",
        _esc(t("tg.subagents", lang, state=state)),
        _esc(t("tg.code_mode.profile", lang, mode=pres)),
        "",
        f"<i>{_esc(t('tg.subagent_types.hint', lang))}</i>",
        "",
    ]
    if not chunk:
        lines.append(_esc(t("tg.subagent_types.empty", lang)))
    for name in chunk:
        meta = _type_meta(host, name)
        badge = (
            t("tg.subagent_types.builtin", lang)
            if meta.get("builtin")
            else t("tg.subagent_types.custom", lang)
        )
        desc = str(meta.get("description") or "—")[:80]
        lines.append(f"• <code>{_esc(name)}</code> <i>{_esc(badge)}</i>")
        lines.append(f"  {_esc(desc)}")
    return "\n".join(lines)


def format_detail_text(host: Any) -> str:
    lang = _lang(host)
    name = _current_type(host)
    if not name:
        return format_list_text(host)
    meta = _type_meta(host, name)
    badge = (
        t("tg.subagent_types.builtin", lang)
        if meta.get("builtin")
        else t("tg.subagent_types.custom", lang)
    )
    temp = meta.get("temperature")
    temp_s = f"{temp:.1f}" if isinstance(temp, (int, float)) else "—"
    model = str(meta.get("model_slot") or "").strip()
    if not model or model.lower() in _INHERIT_SLOTS:
        model = t("tg.subagent_types.inherit_model", lang)
    pres = str(meta.get("tools_presentation") or "native")
    prompt = str(meta.get("system_prompt") or "").strip()
    preview = prompt[:500] + ("…" if len(prompt) > 500 else "")
    tools = ", ".join(str(x) for x in (meta.get("tools") or [])[:12]) or "—"
    extra = len(meta.get("tools") or []) - 12
    if extra > 0:
        tools = f"{tools}, +{extra}"
    lines = [
        f"<b>{_esc(name)}</b> <i>{_esc(badge)}</i>",
        _esc(str(meta.get("description") or "—")),
        "",
        f"{_esc(t('tg.subagent_types.model', lang))}: <code>{_esc(model)}</code>",
        f"{_esc(t('tg.subagent_types.temp', lang))}: <code>{_esc(temp_s)}</code>",
        f"{_esc(t('tg.subagent_types.presentation', lang))}: <code>{_esc(pres)}</code>",
        f"{_esc(t('tg.subagent_types.tools', lang))}: <code>{_esc(tools)}</code>",
        "",
        f"<b>{_esc(t('tg.subagent_types.personality', lang))}</b>",
        f"<pre>{_esc(preview or '—')}</pre>",
    ]
    return "\n".join(lines)


def format_tools_text(host: Any) -> str:
    lang = _lang(host)
    name = _current_type(host)
    if not name:
        return format_list_text(host)
    meta = _type_meta(host, name)
    enabled = set(meta.get("tools") or [])
    lines = [
        f"<b>{_esc(name)}</b> — {_esc(t('tg.subagent_types.tools', lang))}",
        f"<i>{_esc(t('tg.subagent_types.tools_hint', lang))}</i>",
        "",
    ]
    for tool in SUBAGENT_TOOL_CHOICES:
        mark = "✓" if tool in enabled else "·"
        lines.append(f"{mark} <code>{_esc(tool)}</code>")
    return "\n".join(lines)


def list_keyboard_rows(host: Any) -> list[list[tuple[str, str, str]]]:
    """Rows of (label, action, value)."""
    lang = _lang(host)
    on = is_subagents_enabled_for_host(host)
    pres = presentation_for_host(host)
    names = _refresh_names(host)
    session = _session(host)
    page = int(getattr(session, "ui_subagent_page", 0) or 0)
    n_pages = max(1, (len(names) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, n_pages - 1))
    if session is not None:
        session.ui_subagent_page = page
    start = page * PAGE_SIZE
    chunk = names[start : start + PAGE_SIZE]
    rows: list[list[tuple[str, str, str]]] = [
        [
            (f"{_mark(on)}{t('tg.subagents_on', lang)}", "sa", "1"),
            (f"{_mark(not on)}{t('tg.subagents_off', lang)}", "sa", "0"),
        ],
        [(f"{_mark(pres == p)}{p}", "tp", p) for p in PRESENTATIONS],
    ]
    type_row: list[tuple[str, str, str]] = []
    for i, name in enumerate(chunk):
        type_row.append((name[:18], "sd", str(i)))
        if len(type_row) == 2:
            rows.append(type_row)
            type_row = []
    if type_row:
        rows.append(type_row)
    nav: list[tuple[str, str, str]] = []
    if page > 0:
        nav.append(("‹", "sl", str(page - 1)))
    if page + 1 < n_pages:
        nav.append(("›", "sl", str(page + 1)))
    if nav:
        rows.append(nav)
    rows.append([(t("tg.subagent_types.create", lang), "sc", "x")])
    return rows


def detail_keyboard_rows(host: Any) -> list[list[tuple[str, str, str]]]:
    lang = _lang(host)
    name = _current_type(host)
    meta = _type_meta(host, name) if name else {}
    cur_pres = str(meta.get("tools_presentation") or "native")
    cur_temp = meta.get("temperature")
    cur_model = str(meta.get("model_slot") or "").strip()
    rows: list[list[tuple[str, str, str]]] = [
        [(f"{_mark(cur_pres == p)}{p}", "cm", p) for p in PRESENTATIONS],
        [(f"{_mark(_temp_eq(cur_temp, v))}{v:g}", "su", str(i)) for i, v in enumerate(TEMPS[:3])],
        [
            (f"{_mark(_temp_eq(cur_temp, v))}{v:g}", "su", str(i + 3))
            for i, v in enumerate(TEMPS[3:])
        ],
    ]
    options = _model_options(host)
    session = _session(host)
    page = int(getattr(session, "ui_subagent_model_page", 0) or 0)
    n_pages = max(1, (len(options) + MODEL_PAGE_SIZE - 1) // MODEL_PAGE_SIZE)
    page = max(0, min(page, n_pages - 1))
    if session is not None:
        session.ui_subagent_model_page = page
    start = page * MODEL_PAGE_SIZE
    chunk = options[start : start + MODEL_PAGE_SIZE]
    model_row: list[tuple[str, str, str]] = []
    for i, (label, slot) in enumerate(chunk):
        selected = _model_selected(cur_model, slot)
        model_row.append((f"{_mark(selected)}{label[:16]}", "sm", str(i)))
        if len(model_row) == 2:
            rows.append(model_row)
            model_row = []
    if model_row:
        rows.append(model_row)
    nav: list[tuple[str, str, str]] = []
    if page > 0:
        nav.append(("‹", "ml", str(page - 1)))
    if page + 1 < n_pages:
        nav.append(("›", "ml", str(page + 1)))
    if nav:
        rows.append(nav)
    rows.append(
        [
            (t("tg.subagent_types.gen_personality", lang), "sg", "x"),
            (t("tg.subagent_types.write_personality", lang), "swp", "x"),
        ]
    )
    rows.append(
        [
            (t("tg.subagent_types.write_desc", lang), "ds", "x"),
            (t("tg.subagent_types.tools", lang), "tv", "x"),
        ]
    )
    extra: list[tuple[str, str, str]] = []
    if meta.get("builtin"):
        extra.append((t("tg.subagent_types.reset", lang), "sz", "x"))
    elif _confirm(host) == "delete":
        extra.append((t("tg.subagent_types.delete_confirm", lang), "sx", "1"))
    else:
        extra.append((t("tg.subagent_types.delete", lang), "sx", "x"))
    extra.append((t("tg.subagent_types.back", lang), "sb", "x"))
    rows.append(extra)
    return rows


def tools_keyboard_rows(host: Any) -> list[list[tuple[str, str, str]]]:
    lang = _lang(host)
    name = _current_type(host)
    meta = _type_meta(host, name) if name else {}
    enabled = set(meta.get("tools") or [])
    rows: list[list[tuple[str, str, str]]] = []
    pair: list[tuple[str, str, str]] = []
    for i, tool in enumerate(SUBAGENT_TOOL_CHOICES):
        pair.append((f"{_mark(tool in enabled)}{tool}", "tt", str(i)))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([(t("tg.subagent_types.back", lang), "sb", "x")])
    return rows


def _model_options(host: Any) -> list[tuple[str, str]]:
    options: list[tuple[str, str]] = [
        (t("tg.subagent_types.inherit_model", _lang(host)), ""),
    ]
    try:
        from core.models.menu import build_model_choices

        seen: set[str] = set(_INHERIT_SLOTS)
        for choice in build_model_choices(_profile(host), max_provider_models=12):
            slot = str(choice.slot_id or "").strip()
            if slot.lower() in seen:
                continue
            seen.add(slot.lower())
            label = str(choice.label or choice.model or slot)
            options.append((label, slot))
    except Exception:
        logger.debug("model menu failed", exc_info=True)
    return options


def _model_selected(current: str, slot: str) -> bool:
    cur = (current or "").strip().lower()
    key = (slot or "").strip().lower()
    if key in _INHERIT_SLOTS:
        return cur in _INHERIT_SLOTS
    return cur == key


def _temp_eq(current: Any, value: float) -> bool:
    try:
        return abs(float(current) - float(value)) < 0.05
    except (TypeError, ValueError):
        return False


def _mark(on: bool) -> str:
    return "✓ " if on else ""


def _esc(text: str) -> str:
    from integrations.telegram.markdown import escape_html

    return escape_html(str(text or ""))


async def _notify_host(host: Any, text: str) -> None:
    if not text:
        return
    for attr in ("_send_plain", "_send_text"):
        fn = getattr(host, attr, None)
        if callable(fn):
            try:
                await fn(text)
            except Exception:
                logger.debug("subagent UI notify failed", exc_info=True)
            return


async def handle_subagent_types_action(host: Any, action: str, value: str) -> str:
    """Apply a callback. Returns a short toast (may be empty)."""
    lang = _lang(host)
    if action == "tp":
        mode = set_presentation_for_host(host, value)
        return t("tg.code_mode.set", lang, mode=mode)
    if action == "sl":
        session = _session(host)
        if session is not None:
            try:
                session.ui_subagent_page = max(0, int(value))
            except ValueError:
                session.ui_subagent_page = 0
        return ""
    if action == "sd":
        names = _names(host)
        session = _session(host)
        page = int(getattr(session, "ui_subagent_page", 0) or 0)
        try:
            idx = int(value)
        except ValueError:
            return t("tg.error", lang)
        start = page * PAGE_SIZE
        if 0 <= idx < len(names[start : start + PAGE_SIZE]):
            _set_current(host, names[start + idx])
        return ""
    if action == "sb":
        if is_tools_view(host):
            _set_tools_view(host, False)
            return ""
        _set_current(host, "")
        _set_pending(host, None)
        return ""
    if action == "sc":
        _set_pending(host, "create")
        return t("tg.subagent_types.create_prompt", lang)
    if action == "swp":
        if not _current_type(host):
            return t("tg.error", lang)
        _set_pending(host, "personality")
        return t("tg.subagent_types.personality_prompt", lang)
    if action == "ds":
        if not _current_type(host):
            return t("tg.error", lang)
        _set_pending(host, "description")
        return t("tg.subagent_types.desc_prompt", lang)
    if action == "tv":
        if not _current_type(host):
            return t("tg.error", lang)
        _set_tools_view(host, True)
        return ""
    if action == "tt":
        return _toggle_tool(host, value)
    if action == "sg":
        return await _generate_personality(host)
    if action == "su":
        return _set_temperature(host, value)
    if action == "cm":
        return _set_type_presentation(host, value)
    if action == "sm":
        return _set_type_model(host, value)
    if action == "ml":
        session = _session(host)
        if session is not None:
            try:
                session.ui_subagent_model_page = max(0, int(value))
            except ValueError:
                session.ui_subagent_model_page = 0
        return ""
    if action == "sx":
        return _delete_current(host, confirm=value == "1")
    if action == "sz":
        return _reset_overlay(host)
    return ""


async def try_consume_compose(host: Any, text: str) -> str | None:
    """Consume the next chat message if a compose step is pending.

    Returns ``None`` when nothing is pending. Otherwise a toast (possibly empty).
    """
    kind = _pending(host)
    if not kind:
        return None
    body = (text or "").strip()
    if body.lower() in _COMPOSE_CANCEL:
        _set_pending(host, None)
        return ""
    if not body:
        lang = _lang(host)
        if kind == "create":
            return t("tg.subagent_types.create_prompt", lang)
        if kind == "personality":
            return t("tg.subagent_types.personality_prompt", lang)
        return t("tg.subagent_types.desc_prompt", lang)
    _set_pending(host, None)
    if kind == "create":
        return await _create_from_brief(host, body)
    if kind == "personality":
        return await _write_personality(host, body)
    if kind == "description":
        return _write_description(host, body)
    return ""


async def _create_from_brief(host: Any, brief: str) -> str:
    from core.subagents.from_description import build_custom_type_from_brief_async

    lang = _lang(host)
    await _notify_host(host, t("tg.subagent_types.working", lang))
    profile = _profile(host)
    try:
        store = SubAgentTypeStore(profile)
        existing = list(store.load_types().keys()) + [
            i["name"] for i in list_available_subagents(profile=profile)
        ]
        agent = getattr(host, "agent", None)
        client = getattr(agent, "client", None) if agent is not None else None
        model = getattr(agent, "model", None) if agent is not None else None
        custom = await build_custom_type_from_brief_async(
            brief,
            existing_names=existing,
            profile=profile,
            client=client,
            model=model,
        )
        store.upsert(custom)
        sync_custom_type_profile_bindings(profile, custom)
        if custom.tools_presentation:
            set_presentation_for_host(host, custom.tools_presentation, slot=custom.name)
        _refresh_names(host)
        _set_current(host, custom.name)
        return t("tg.subagent_types.created", lang, name=custom.name)
    except Exception as exc:
        logger.exception("create sub-agent type from brief failed")
        return t("tg.subagent_types.create_fail", lang, error=str(exc)[:200])


async def _write_personality(host: Any, brief: str) -> str:
    name = _current_type(host)
    lang = _lang(host)
    if not name:
        return t("tg.error", lang)
    from core.subagents.from_description import expand_system_prompt, expand_system_prompt_via_llm

    await _notify_host(host, t("tg.subagent_types.working", lang))
    agent = getattr(host, "agent", None)
    try:
        prompt = await expand_system_prompt_via_llm(
            brief,
            profile=_profile(host),
            client=getattr(agent, "client", None) if agent is not None else None,
            model=getattr(agent, "model", None) if agent is not None else None,
        )
    except Exception:
        logger.debug("personality LLM expand failed", exc_info=True)
        prompt = None
    prompt = (prompt or "").strip() or expand_system_prompt(brief)
    _save_personality(host, name, prompt)
    return t("tg.subagent_types.personality_done", lang, name=name)


def _write_description(host: Any, brief: str) -> str:
    name = _current_type(host)
    lang = _lang(host)
    if not name:
        return t("tg.error", lang)
    desc = " ".join((brief or "").split())[:240]
    profile = _profile(host)
    custom = SubAgentTypeStore(profile).get(name)
    if custom is not None:
        custom.description = desc
        SubAgentTypeStore(profile).upsert(custom)
    else:
        SubAgentOverlayStore(profile).merge(name, description=desc)
    _refresh_names(host)
    return t("tg.subagent_types.desc_done", lang, name=name)


async def _generate_personality(host: Any) -> str:
    name = _current_type(host)
    if not name:
        return t("tg.error", _lang(host))
    meta = _type_meta(host, name)
    brief = (
        f"Sub-agent type `{name}`. {meta.get('description') or ''}\n"
        f"Current personality:\n{str(meta.get('system_prompt') or '')[:800]}"
    )
    return await _write_personality(host, brief)


def _save_personality(host: Any, name: str, prompt: str) -> None:
    profile = _profile(host)
    custom = SubAgentTypeStore(profile).get(name)
    if custom is not None:
        custom.system_prompt = prompt
        SubAgentTypeStore(profile).upsert(custom)
        return
    SubAgentOverlayStore(profile).merge(name, system_prompt=prompt)


def _set_temperature(host: Any, value: str) -> str:
    name = _current_type(host)
    if not name:
        return t("tg.error", _lang(host))
    try:
        temp = TEMPS[int(value)]
    except (ValueError, IndexError):
        return t("tg.error", _lang(host))
    profile = _profile(host)
    custom = SubAgentTypeStore(profile).get(name)
    if custom is not None:
        custom.temperature = float(temp)
        SubAgentTypeStore(profile).upsert(custom)
    else:
        SubAgentOverlayStore(profile).merge(name, temperature=float(temp))
    return t("tg.subagent_types.temp_set", _lang(host), name=name, value=f"{temp:g}")


def _set_type_presentation(host: Any, value: str) -> str:
    name = _current_type(host)
    if not name:
        return t("tg.error", _lang(host))
    mode = set_presentation_for_host(host, value, slot=name)
    profile = _profile(host)
    custom = SubAgentTypeStore(profile).get(name)
    if custom is not None:
        custom.tools_presentation = mode
        SubAgentTypeStore(profile).upsert(custom)
    else:
        SubAgentOverlayStore(profile).merge(name, tools_presentation=mode)
    return t("tg.subagent_types.presentation_set", _lang(host), name=name, mode=mode)


def _set_type_model(host: Any, value: str) -> str:
    name = _current_type(host)
    if not name:
        return t("tg.error", _lang(host))
    options = _model_options(host)
    session = _session(host)
    page = int(getattr(session, "ui_subagent_model_page", 0) or 0)
    start = page * MODEL_PAGE_SIZE
    try:
        idx = int(value)
        _label, slot = options[start + idx]
    except (ValueError, IndexError):
        return t("tg.error", _lang(host))
    profile = _profile(host)
    custom = SubAgentTypeStore(profile).get(name)
    if custom is not None:
        custom.model_slot = slot
        SubAgentTypeStore(profile).upsert(custom)
        sync_custom_type_profile_bindings(profile, custom)
    else:
        SubAgentOverlayStore(profile).merge(name, model_slot=slot or None)
        _persist_overlay_model(profile, name, slot)
    return t("tg.subagent_types.model_set", _lang(host), name=name)


def _toggle_tool(host: Any, value: str) -> str:
    name = _current_type(host)
    lang = _lang(host)
    if not name:
        return t("tg.error", lang)
    try:
        idx = int(value)
        tool = SUBAGENT_TOOL_CHOICES[idx]
    except (ValueError, IndexError):
        return t("tg.error", lang)
    meta = _type_meta(host, name)
    current = [str(x) for x in (meta.get("tools") or []) if str(x).strip()]
    if tool in current:
        nxt = [x for x in current if x != tool]
        if not nxt:
            return t("tg.subagent_types.tools_min", lang)
    else:
        nxt = current + [tool]
    profile = _profile(host)
    custom = SubAgentTypeStore(profile).get(name)
    if custom is not None:
        custom.tools = nxt
        SubAgentTypeStore(profile).upsert(custom)
    else:
        SubAgentOverlayStore(profile).merge(name, tools=nxt)
    state = "on" if tool in nxt else "off"
    return t("tg.subagent_types.tool_toggled", lang, tool=tool, state=state)


def _persist_overlay_model(profile: str, type_name: str, model_slot: str) -> None:
    from cli.core import get_profile_manager
    from core.subagents.store import resolve_model_slot_binding

    manager = get_profile_manager()
    config = manager.load_profile(profile)
    agent_models = dict(getattr(config, "agent_models", None) or {})
    slot = (model_slot or "").strip()
    if slot and slot.lower() not in _INHERIT_SLOTS:
        resolved = resolve_model_slot_binding(profile, slot)
        if resolved:
            entry = {"provider": resolved[0], "model": resolved[1]}
            agent_models[slot] = entry
            agent_models[type_name] = entry
            config.agent_models = agent_models
            manager.save_profile(profile, config)
            return
    if type_name in agent_models and type_name != "main":
        del agent_models[type_name]
        config.agent_models = agent_models
        manager.save_profile(profile, config)


def _delete_current(host: Any, *, confirm: bool) -> str:
    name = _current_type(host)
    lang = _lang(host)
    if not name or is_builtin_subagent(name):
        return t("tg.error", lang)
    if not confirm:
        _set_confirm(host, "delete")
        return t("tg.subagent_types.delete_hint", lang, name=name)
    profile = _profile(host)
    removed = SubAgentTypeStore(profile).remove(name)
    if removed is None:
        return t("tg.error", lang)
    cleanup_custom_type_profile_bindings(profile, name)
    SubAgentOverlayStore(profile).remove(name)
    clear_slot_presentation_for_host(host, name)
    _set_current(host, "")
    _refresh_names(host)
    return t("tg.subagent_types.deleted", lang, name=name)


def _reset_overlay(host: Any) -> str:
    name = _current_type(host)
    lang = _lang(host)
    if not name:
        return t("tg.error", lang)
    SubAgentOverlayStore(_profile(host)).remove(name)
    clear_slot_presentation_for_host(host, name)
    return t("tg.subagent_types.reset_done", lang, name=name)
