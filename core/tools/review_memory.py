"""Show long-term facts and apply only the forgets and rewrites the user picks."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from core.memory.review import analyze_memory_items
from core.tools.ask_user import parse_ask_user_reply
from core.tools.base import BaseTool
from core.tools.execution_context import (
    get_interaction_bridge,
    get_memory_facade,
    get_profile_name,
    get_subagent_name,
    get_tools_registry,
)
from core.tools.result import tool_err, tool_ok

_MAX_FACTS = 32
_PAGE = 8


class ReviewMemoryTool(BaseTool):
    """List remembered facts, suggest stale ones, then let the user decide."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "review_memory"
        self.description = (
            "Correct memory with the user. action=review lists keyed facts, "
            "episode summaries, and whole conversations, each with content, "
            "updated_at, and a suggestion (keep, forget, or revise). "
            "action=confirm asks the user; the question quotes what each row "
            "stores. Unselected rows stay. action=apply deletes immediately "
            "and does not ask: use it only when the user already said what to "
            "drop, including keep_days (for example keep the last 7 days and "
            "delete the rest). keep_days never deletes the current session; "
            "put that key in forget to remove it too. Forgetting a session "
            "removes its transcript, search snippets, and episode summaries. "
            "Forgetting one episode removes that summary only. Do not say a "
            "row was removed until apply or confirm lists it in forgotten."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "additionalProperties": False,
            "required": ["action"],
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["review", "confirm", "apply"],
                    "description": (
                        "review lists rows. confirm asks the user. "
                        "apply deletes now because the user already said what to drop."
                    ),
                },
                "forget": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Keys to drop. On confirm the user can ignore these. "
                        "On apply they are deleted without another question."
                    ),
                },
                "keep_days": {
                    "type": "integer",
                    "description": (
                        "With action=apply, delete every row older than this many days. "
                        "The current session stays unless its key is also in forget."
                    ),
                },
                "revisions": {
                    "type": "array",
                    "description": "Rewrites to offer. Applied only if the user accepts.",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["key", "content"],
                        "properties": {
                            "key": {"type": "string"},
                            "content": {"type": "string"},
                        },
                    },
                },
            },
        }

    async def execute(
        self,
        action: str = "review",
        forget: list[str] | None = None,
        revisions: list[dict[str, Any]] | None = None,
        keep_days: int | None = None,
        **_: Any,
    ) -> str:
        memory = _resolve_memory()
        stores = _stores(memory)
        if stores is None:
            return tool_err("memory_disabled", "Long-term memory is disabled for this profile.")
        items = analyze_memory_items(await _load_items(stores))
        if action == "review":
            shown = _prioritize(items)[:_MAX_FACTS]
            return tool_ok(
                action="review",
                count=len(items),
                shown=len(shown),
                facts=shown,
                note=_review_note(len(items), len(shown)),
            )
        if action == "apply":
            try:
                days = _parse_keep_days(keep_days)
            except ValueError:
                return tool_err("bad_keep_days", "keep_days must be an integer from 0 to 3650")
            keys = [str(key).strip() for key in (forget or []) if str(key).strip()]
            if days is None and not keys:
                return tool_err(
                    "nothing_to_apply",
                    "Pass forget and/or keep_days. Nothing was deleted.",
                )
            forgotten = await _apply_forget(stores, items, keys=keys, keep_days=days)
            return tool_ok(action="apply", forgotten=forgotten, keep_days=days)
        if action != "confirm":
            return tool_err("bad_action", "action must be review, confirm, or apply")

        known = {(item["kind"], item["key"]): item for item in items}
        offered = _prioritize(items)[:_MAX_FACTS]
        rewrite = _clean_revisions(revisions, known)
        if not offered and not rewrite:
            return tool_ok(
                action="confirm", forgotten=[], revised=[], kept=[], note="No facts stored."
            )

        bridge = _resolve_bridge()
        if bridge is None or not callable(getattr(bridge, "ask_user", None)):
            return tool_err(
                "no_bridge",
                "Cannot ask the user in this session. Show the review list in the reply "
                "and call confirm again where ask_user works. Nothing was deleted.",
                facts=offered,
            )

        locale = _locale()
        questions, id_map = _questions(
            offered,
            agent_forget={str(key).strip() for key in (forget or []) if str(key).strip()},
            revisions=rewrite,
            locale=locale,
        )
        if not questions:
            return tool_ok(
                action="confirm", forgotten=[], revised=[], kept=[], note="No facts stored."
            )
        try:
            raw = await bridge.ask_user(
                get_subagent_name() or "main",
                questions[0]["prompt"],
                context="",
                questions=questions,
            )
        except Exception as exc:
            return tool_err("error", str(exc))

        text = str(raw or "")
        if "timed out" in text.lower() or text.strip().endswith("timeout"):
            return tool_err("timeout", "no answer from user")
        answers = parse_ask_user_reply(text, questions)
        forget_ids = _selected_ids(answers, prefix="forget_")
        forgotten: list[str] = []
        for option_id in forget_ids:
            ref = id_map.get(option_id)
            if ref is None:
                continue
            kind, key = ref
            removed = await _delete(stores, kind, key)
            if removed:
                forgotten.append(key)

        revised: list[str] = []
        semantic = stores[0]
        strategic = stores[1]
        if rewrite and _accepted_revisions(answers):
            for row in rewrite:
                if _kind_of(known, row["key"]) == "strategic":
                    stored = known[("strategic", row["key"])]
                    await strategic.store_strategy(
                        key=row["key"],
                        content=row["content"],
                        category=str(stored.get("category") or "general"),
                        source="user_review",
                    )
                else:
                    await semantic.store_fact(row["key"], row["content"], source="user_review")
                revised.append(row["key"])

        kept = [item["key"] for item in offered if item["key"] not in forgotten]
        return tool_ok(
            action="confirm",
            forgotten=forgotten,
            revised=revised,
            kept=kept,
        )


def _kind_of(known: dict[tuple[str, str], dict[str, Any]], key: str) -> str:
    if ("strategic", key) in known and ("semantic", key) not in known:
        return "strategic"
    return "semantic"


def _clean_revisions(
    revisions: list[dict[str, Any]] | None,
    known: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in revisions or []:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key") or "").strip()
        content = str(raw.get("content") or "").strip()
        if not key or not content or key in seen:
            continue
        if ("semantic", key) not in known and ("strategic", key) not in known:
            continue
        seen.add(key)
        out.append({"key": key, "content": content})
    return out[:8]


def _questions(
    offered: list[dict[str, Any]],
    *,
    agent_forget: set[str],
    revisions: list[dict[str, str]],
    locale: str,
) -> tuple[list[dict[str, Any]], dict[str, tuple[str, str]]]:
    ru = locale.startswith("ru")
    current = _current_conversation_id()
    # One page: Telegram and the TUI show a single question, and buttons are short.
    pages = [offered[:_PAGE]] if offered else []
    questions: list[dict[str, Any]] = []
    id_map: dict[str, tuple[str, str]] = {}
    for page_index, page in enumerate(pages):
        options = []
        described: list[dict[str, Any]] = []
        for item in page:
            option_id = f"m{len(id_map)}"
            id_map[option_id] = (str(item["kind"]), str(item["key"]))
            suggestion = str(item.get("suggestion") or "keep")
            reason = str(item.get("reason") or "")
            if item["key"] in agent_forget and suggestion == "keep":
                suggestion = "forget"
                reason = "agent recommends forgetting"
            described.append({**item, "suggestion": suggestion, "reason": reason})
            content = _clip(str(item.get("content") or ""), 48) or ("пусто" if ru else "empty")
            options.append(
                {
                    "id": option_id,
                    "label": f"{len(options) + 1}. {content}",
                    "description": _effect(str(item.get("kind") or ""), ru=ru),
                }
            )
        prompt = _catalog_prompt(described, ru=ru, current=current, page_index=page_index)
        questions.append(
            {
                "id": f"forget_{page_index}",
                "prompt": prompt,
                "header": "Memory",
                "allow_free_text": False,
                "multi_select": True,
                "options": options,
            }
        )
    if revisions:
        lines = [f"{row['key']}: {row['content']}" for row in revisions]
        questions.append(
            {
                "id": "apply_revisions",
                "prompt": (
                    "Применить эти правки?\n" + "\n".join(lines)
                    if ru
                    else "Apply these rewrites?\n" + "\n".join(lines)
                ),
                "header": "Memory",
                "allow_free_text": False,
                "multi_select": False,
                "options": [
                    {"id": "yes", "label": "Применить" if ru else "Apply"},
                    {"id": "no", "label": "Не менять текст" if ru else "Leave text"},
                ],
            }
        )
    return questions, id_map


def _selected_ids(answers: dict[str, list[str]], *, prefix: str) -> list[str]:
    chosen: list[str] = []
    for key, values in answers.items():
        if not str(key).startswith(prefix):
            continue
        chosen.extend(str(value) for value in values)
    return chosen


def _accepted_revisions(answers: dict[str, list[str]]) -> bool:
    values = [item.lower() for item in answers.get("apply_revisions", [])]
    return any(item in {"yes", "apply", "да", "применить"} for item in values)


_KIND_RANK = {"conversation": 0, "episodic": 1, "semantic": 2, "strategic": 3}


def _prioritize(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rank = {"forget": 0, "revise": 1, "keep": 2}
    by_time = sorted(items, key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return sorted(
        by_time,
        key=lambda item: (
            rank.get(str(item.get("suggestion")), 9),
            _KIND_RANK.get(str(item.get("kind")), 9),
            str(item.get("key") or ""),
        ),
    )


def _clip(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def _review_note(count: int, shown: int) -> str:
    note = (
        "Facts, episode summaries, and whole sessions are included. "
        "Add your own judgment, then call review_memory action=confirm. "
        "Nothing was deleted."
    )
    hidden = count - shown
    if hidden > 0:
        note += f" {hidden} older rows are not on this page; review again after this pass."
    return note


def _current_conversation_id() -> str:
    from core.tools.execution_context import get_conversation_id

    return str(get_conversation_id() or "").strip()


def _catalog_prompt(
    page: list[dict[str, Any]],
    *,
    ru: bool,
    current: str,
    page_index: int,
) -> str:
    if ru:
        intro = (
            "Ещё записи. Отметьте номера, которые удалить."
            if page_index
            else "Отметьте номера, которые удалить. Ниже написано, что хранится. "
            "Неотмеченное останется."
        )
    else:
        intro = (
            "More rows. Select the numbers to delete."
            if page_index
            else "Select the numbers to delete. Each block is what is stored. Unselected rows stay."
        )
    lines = [intro, ""]
    for index, item in enumerate(page, start=1):
        lines.append(_catalog_block(index, item, ru=ru, current=current))
    return "\n".join(lines)


def _catalog_block(index: int, item: dict[str, Any], *, ru: bool, current: str) -> str:
    kind = str(item.get("kind") or "")
    key = str(item.get("key") or "")
    when = _clip(str(item.get("updated_at") or ""), 19)
    title = _kind_title(kind, ru=ru)
    content = _clip(str(item.get("content") or ""), 180) or ("пусто" if ru else "empty")
    ident = ""
    if kind == "conversation":
        ident = f" {_clip(key, 48)}"
        if current and key == current:
            ident += ", этот чат" if ru else ", this chat"
    elif kind == "episodic":
        ident = f" #{key}"
        conversation_id = str(item.get("conversation_id") or "")
        if conversation_id:
            ident += (
                f", сессия {_clip(conversation_id, 40)}"
                if ru
                else f", session {_clip(conversation_id, 40)}"
            )
    elif key:
        ident = f" {key}"
    date = f", {when}" if when else ""
    return f"{index}. {title}{ident}{date}\n{content}\n{_effect(kind, ru=ru)}"


def _kind_title(kind: str, *, ru: bool) -> str:
    titles = {
        "semantic": ("Факт", "Fact"),
        "strategic": ("Правило", "Strategy"),
        "episodic": ("Сводка", "Summary"),
        "conversation": ("Диалог", "Conversation"),
    }
    ru_title, en_title = titles.get(kind, ("Запись", "Row"))
    return ru_title if ru else en_title


def _effect(kind: str, *, ru: bool) -> str:
    if kind == "conversation":
        return (
            "Удалится переписка, поиск по ней и сводки этой сессии."
            if ru
            else "Deletes the transcript, its search snippets, and its summaries."
        )
    if kind == "episodic":
        return (
            "Удалится только эта сводка. Переписка останется."
            if ru
            else "Deletes this summary only. The transcript stays."
        )
    return "Удалится эта запись." if ru else "Deletes this row."


def _parse_keep_days(value: Any) -> int | None:
    if value is None or value == "":
        return None
    days = int(value)
    if days < 0 or days > 3650:
        raise ValueError
    return days


def _parse_time(raw: str) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1]
    if " " in text and "T" not in text:
        text = text.replace(" ", "T", 1)
    try:
        parsed = datetime.fromisoformat(text[:26])
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


async def _apply_forget(
    stores: tuple[Any, Any, Any, Any],
    items: list[dict[str, Any]],
    *,
    keys: list[str],
    keep_days: int | None,
) -> list[str]:
    current = _current_conversation_id()
    chosen: dict[tuple[str, str], None] = {}
    by_key: dict[str, list[tuple[str, str]]] = {}
    for item in items:
        ref = (str(item.get("kind") or ""), str(item.get("key") or ""))
        if not ref[1]:
            continue
        by_key.setdefault(ref[1], []).append(ref)
    for key in keys:
        for ref in by_key.get(key, []):
            chosen[ref] = None
    if keep_days is not None:
        cutoff = datetime.now() - timedelta(days=keep_days)
        for item in items:
            kind = str(item.get("kind") or "")
            key = str(item.get("key") or "")
            if not key:
                continue
            if kind == "conversation" and current and key == current:
                continue
            when = _parse_time(str(item.get("updated_at") or ""))
            if when is not None and when < cutoff:
                chosen[(kind, key)] = None
    forgotten: list[str] = []
    order = {"conversation": 0, "episodic": 1, "semantic": 2, "strategic": 3}
    for kind, key in sorted(chosen, key=lambda ref: (order.get(ref[0], 9), ref[1])):
        if await _delete(stores, kind, key):
            forgotten.append(key)
    return forgotten


async def _load_items(
    stores: tuple[Any, Any, Any, Any],
) -> list[dict[str, Any]]:
    semantic, strategic, episodic, conversations = stores
    items: list[dict[str, Any]] = []
    if semantic is not None:
        for row in await semantic.get_all_facts():
            items.append({**row, "kind": "semantic"})
    if strategic is not None:
        for row in await strategic.get_all_strategies():
            items.append({**row, "kind": "strategic"})
    if episodic is not None:
        for row in await episodic.list_episodes():
            items.append(
                {
                    "kind": "episodic",
                    "key": str(row.get("id") or ""),
                    "content": str(row.get("content") or ""),
                    "updated_at": str(row.get("created_at") or ""),
                    "conversation_id": str(row.get("source") or ""),
                }
            )
    if conversations is not None:
        for row in await conversations.list_conversations_for_review():
            count = int(row.get("message_count") or 0)
            preview = str(row.get("preview") or "").strip()
            content = f"{count} messages."
            if preview:
                content = f"{content} {preview}"
            items.append(
                {
                    "kind": "conversation",
                    "key": str(row.get("conversation_id") or ""),
                    "content": content,
                    "updated_at": str(row.get("last_timestamp") or ""),
                }
            )
    return items


async def _delete(stores: tuple[Any, Any, Any, Any], kind: str, key: str) -> bool:
    semantic, strategic, episodic, conversations = stores
    if kind == "strategic":
        if strategic is None:
            return False
        return bool(await strategic.delete_strategy(key))
    if kind == "episodic":
        if episodic is None:
            return False
        return bool(await episodic.delete_episode(key))
    if kind == "conversation":
        if conversations is None:
            return False
        deleted = bool(await conversations.delete_conversation(key))
        if episodic is not None:
            await episodic.delete_episodes_for_conversation(key)
        return deleted
    if semantic is None:
        return False
    return bool(await semantic.delete_fact(key))


def _stores(memory: Any) -> tuple[Any, Any, Any, Any] | None:
    if memory is None:
        return None
    config = getattr(memory, "config", None)
    ltm_on = config is None or getattr(config, "enable_long_term_memory", True)
    semantic = strategic = episodic = None
    if ltm_on:
        try:
            semantic = memory.semantic
            strategic = memory.strategic
            episodic = getattr(memory, "episodic", None)
        except RuntimeError:
            semantic = strategic = episodic = None
    conversations = getattr(memory, "conversations", None)
    if semantic is None and strategic is None and episodic is None and conversations is None:
        return None
    return semantic, strategic, episodic, conversations


def _resolve_memory() -> Any:
    facade = get_memory_facade()
    if facade is not None:
        return facade
    from core.di import resolve_runtime_config
    from core.memory.facade import MemoryFacade
    from core.profile import ProfileManager

    profile_name = (get_profile_name() or "").strip()
    if profile_name:
        manager = ProfileManager()
        if manager.profile_exists(profile_name):
            return MemoryFacade(resolve_runtime_config(manager.load_profile(profile_name)))
    return MemoryFacade(resolve_runtime_config())


def _resolve_bridge() -> Any | None:
    bridge = get_interaction_bridge()
    if bridge is not None:
        return bridge
    registry = get_tools_registry()
    host = getattr(registry, "_host_agent", None) if registry is not None else None
    if host is None:
        return None
    return getattr(getattr(host, "subagents", None), "interactions", None)


def _locale() -> str:
    profile = (get_profile_name() or "default").strip() or "default"
    try:
        from core.i18n.locale import LocaleStore

        return LocaleStore(profile).get()
    except Exception:
        return "ru"
