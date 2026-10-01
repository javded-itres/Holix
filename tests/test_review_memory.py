"""Selective long-term memory review: suggestions, then only the user's choice."""

from __future__ import annotations

import json
from types import SimpleNamespace

import aiosqlite
import pytest
from core.memory.episodic import EpisodicMemoryStore
from core.memory.review import analyze_memory_items
from core.tools.execution_context import reset_subagent_scope, subagent_scope
from core.tools.lazy_schema import CORE_TOOL_NAMES
from core.tools.review_memory import ReviewMemoryTool
from core.tools.slot_policy import PLAN_MODE_BLOCKED, is_plan_mode_blocked, tool_allowed_for_slot


def test_analyze_marks_empty_duplicate_revise_contradiction_and_stale() -> None:
    items = analyze_memory_items(
        [
            {"key": "", "content": "ignored"},
            {"key": "blank", "content": "  ", "updated_at": "2026-01-01"},
            {
                "key": "tea_old",
                "content": "User drinks tea every morning",
                "updated_at": "2026-01-01",
            },
            {
                "key": "tea_new",
                "content": "User drinks tea every morning",
                "updated_at": "2026-03-01",
            },
            {
                "key": "theme",
                "content": "User prefers dark theme",
                "updated_at": "2026-01-01",
            },
            {
                "key": "theme_2",
                "content": "User prefers light theme",
                "updated_at": "2026-04-01",
            },
            {
                "key": "uses_docker",
                "content": "Project uses docker always",
                "updated_at": "2026-01-01",
            },
            {
                "key": "skips_docker",
                "content": "Project never uses docker always",
                "updated_at": "2026-05-01",
            },
            {
                "key": "once",
                "content": "Temporary todo for this session",
                "updated_at": "2026-06-01",
            },
            {
                "key": "stable",
                "content": "User writes in Russian",
                "updated_at": "2026-01-01",
            },
        ]
    )
    by_key = {item["key"]: item for item in items}
    assert "ignored" not in by_key
    assert by_key["blank"]["suggestion"] == "forget"
    assert by_key["blank"]["reason"] == "empty"
    assert by_key["tea_new"]["suggestion"] == "keep"
    assert by_key["tea_old"]["suggestion"] == "forget"
    assert "tea_new" in by_key["tea_old"]["reason"]
    assert by_key["theme_2"]["suggestion"] == "keep"
    assert by_key["theme"]["suggestion"] == "revise"
    assert "theme_2" in by_key["theme"]["reason"]
    assert by_key["uses_docker"]["suggestion"] == "forget"
    assert "skips_docker" in by_key["uses_docker"]["reason"]
    assert by_key["skips_docker"]["suggestion"] == "keep"
    assert by_key["once"]["suggestion"] == "forget"
    assert by_key["stable"]["suggestion"] == "keep"


class _Memory:
    def __init__(self) -> None:
        self.facts = [
            {
                "key": "drop_me",
                "content": "temporary note",
                "updated_at": "2026-01-01",
                "category": "",
            },
            {
                "key": "keep_me",
                "content": "Stable preference for Russian",
                "updated_at": "2026-02-01",
                "category": "",
            },
        ]
        self.strategies = [
            {
                "key": "user_work_style",
                "content": "Short answers",
                "updated_at": "2026-02-02",
                "category": "user_profile",
            }
        ]
        self.episodes: list[dict] = []
        self.sessions: list[dict] = []
        self.deleted: list[tuple[str, str]] = []
        self.deleted_episodes: list[int] = []
        self.deleted_sessions: list[str] = []
        self.deleted_session_episodes: list[str] = []
        self.stored_facts: list[tuple[str, str, str]] = []
        self.stored_strategies: list[tuple[str, str, str]] = []
        self.config = SimpleNamespace(enable_long_term_memory=True)
        self.semantic = self
        self.strategic = self
        self.episodic = self
        self.conversations = self

    async def get_all_facts(self) -> list[dict]:
        return list(self.facts)

    async def get_all_strategies(self) -> list[dict]:
        return list(self.strategies)

    async def delete_fact(self, key: str) -> bool:
        self.deleted.append(("semantic", key))
        return True

    async def delete_strategy(self, key: str) -> bool:
        self.deleted.append(("strategic", key))
        return True

    async def store_fact(self, key: str, content: str, source: str = "") -> int:
        self.stored_facts.append((key, content, source))
        return 1

    async def store_strategy(
        self,
        key: str,
        content: str,
        category: str = "general",
        source: str = "",
        metadata: dict | None = None,
    ) -> int:
        self.stored_strategies.append((key, content, source))
        return 1

    async def list_episodes(self) -> list[dict]:
        return list(self.episodes)

    async def delete_episode(self, entry_id: int) -> bool:
        self.deleted_episodes.append(int(entry_id))
        return True

    async def delete_episodes_for_conversation(self, conversation_id: str) -> int:
        self.deleted_session_episodes.append(conversation_id)
        return 1

    async def list_conversations_for_review(self, limit: int = 200) -> list[dict]:
        return list(self.sessions)[:limit]

    async def delete_conversation(self, conversation_id: str) -> bool:
        self.deleted_sessions.append(conversation_id)
        return True


class _Bridge:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.questions: list[dict] | None = None

    async def ask_user(self, name, question, *, context="", questions=None):
        self.questions = questions
        return self.reply


def _patch(monkeypatch: pytest.MonkeyPatch, memory: _Memory) -> None:
    monkeypatch.setattr("core.tools.review_memory._resolve_memory", lambda: memory)
    monkeypatch.setattr("core.tools.review_memory._locale", lambda: "ru")


async def test_review_lists_facts_and_does_not_delete(monkeypatch: pytest.MonkeyPatch) -> None:
    memory = _Memory()
    _patch(monkeypatch, memory)
    raw = await ReviewMemoryTool().execute(action="review")
    payload = json.loads(raw)
    assert payload["ok"] is True
    assert payload["count"] == 3
    assert payload["facts"][0]["key"] == "drop_me"
    assert payload["facts"][0]["suggestion"] == "forget"
    assert memory.deleted == []
    assert memory.stored_facts == []


async def test_confirm_forgets_only_selected_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    memory = _Memory()
    _patch(monkeypatch, memory)
    bridge = _Bridge(json.dumps({"forget_0": ["m0"]}))
    tokens = subagent_scope("main", interaction_bridge=bridge)
    try:
        raw = await ReviewMemoryTool().execute(
            action="confirm",
            forget=["keep_me"],
        )
    finally:
        reset_subagent_scope(tokens)
    payload = json.loads(raw)
    assert payload["forgotten"] == ["drop_me"]
    assert "keep_me" in payload["kept"]
    assert memory.deleted == [("semantic", "drop_me")]
    assert bridge.questions is not None
    prompt = bridge.questions[0]["prompt"]
    assert prompt.startswith("Отметьте")
    assert "temporary note" in prompt
    assert "Stable preference for Russian" in prompt
    assert "Факт drop_me" in prompt
    assert "Удалится эта запись." in prompt
    labels = [option["label"] for option in bridge.questions[0]["options"]]
    assert any("temporary note" in label for label in labels)


async def test_empty_selection_deletes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    memory = _Memory()
    _patch(monkeypatch, memory)
    bridge = _Bridge(json.dumps({"forget_0": []}))
    tokens = subagent_scope("main", interaction_bridge=bridge)
    try:
        raw = await ReviewMemoryTool().execute(action="confirm", forget=["drop_me", "keep_me"])
    finally:
        reset_subagent_scope(tokens)
    payload = json.loads(raw)
    assert payload["forgotten"] == []
    assert memory.deleted == []


async def test_revisions_apply_only_when_accepted_and_key_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memory = _Memory()
    _patch(monkeypatch, memory)
    revisions = [
        {"key": "keep_me", "content": "Stable preference for short Russian"},
        {"key": "user_work_style", "content": "Long answers"},
        {"key": "missing", "content": "no such fact"},
        {"key": "keep_me", "content": "duplicate revision"},
    ]
    no = _Bridge(json.dumps({"forget_0": [], "apply_revisions": "no"}))
    tokens = subagent_scope("main", interaction_bridge=no)
    try:
        raw = await ReviewMemoryTool().execute(action="confirm", revisions=revisions)
    finally:
        reset_subagent_scope(tokens)
    assert json.loads(raw)["revised"] == []
    assert memory.stored_facts == []
    assert memory.stored_strategies == []

    yes = _Bridge(json.dumps({"forget_0": [], "apply_revisions": ["yes"]}))
    tokens = subagent_scope("main", interaction_bridge=yes)
    try:
        raw = await ReviewMemoryTool().execute(action="confirm", revisions=revisions)
    finally:
        reset_subagent_scope(tokens)
    payload = json.loads(raw)
    assert payload["revised"] == ["keep_me", "user_work_style"]
    assert memory.stored_facts == [
        ("keep_me", "Stable preference for short Russian", "user_review")
    ]
    assert memory.stored_strategies == [("user_work_style", "Long answers", "user_review")]
    assert yes.questions is not None
    assert yes.questions[-1]["id"] == "apply_revisions"
    assert "missing" not in yes.questions[-1]["prompt"]


async def test_confirm_without_bridge_does_not_delete(monkeypatch: pytest.MonkeyPatch) -> None:
    memory = _Memory()
    _patch(monkeypatch, memory)
    raw = await ReviewMemoryTool().execute(action="confirm", forget=["drop_me"])
    payload = json.loads(raw)
    assert payload["ok"] is False
    assert payload["code"] == "no_bridge"
    assert memory.deleted == []


async def test_disabled_memory_and_bad_action(monkeypatch: pytest.MonkeyPatch) -> None:
    memory = _Memory()
    memory.config.enable_long_term_memory = False
    memory.conversations = None
    memory.episodic = None
    _patch(monkeypatch, memory)
    disabled = json.loads(await ReviewMemoryTool().execute(action="review"))
    assert disabled["code"] == "memory_disabled"
    memory.config.enable_long_term_memory = True
    bad = json.loads(await ReviewMemoryTool().execute(action="wipe"))
    assert bad["code"] == "bad_action"


async def test_unknown_revision_alone_stores_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    memory = _Memory()
    memory.facts = []
    memory.strategies = []
    _patch(monkeypatch, memory)
    bridge = _Bridge(json.dumps({"apply_revisions": "yes"}))
    tokens = subagent_scope("main", interaction_bridge=bridge)
    try:
        raw = await ReviewMemoryTool().execute(
            action="confirm",
            revisions=[{"key": "ghost", "content": "nope"}],
        )
    finally:
        reset_subagent_scope(tokens)
    payload = json.loads(raw)
    assert payload["ok"] is True
    assert payload["revised"] == []
    assert bridge.questions is None
    assert memory.stored_facts == []


def test_numeric_episode_ids_are_not_treated_as_rewrites() -> None:
    items = analyze_memory_items(
        [
            {
                "kind": "episodic",
                "key": "1",
                "content": "Deployed the gateway",
                "updated_at": "2026-01-01",
            },
            {
                "kind": "episodic",
                "key": "2",
                "content": "Renamed the service",
                "updated_at": "2026-02-01",
            },
        ]
    )
    assert {item["suggestion"] for item in items} == {"keep"}


async def test_delete_episode_removes_sqlite_row_and_vector(tmp_path) -> None:
    db_path = tmp_path / "ltm.db"
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            CREATE TABLE ltm_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_type TEXT NOT NULL,
                key TEXT,
                content TEXT NOT NULL,
                source TEXT,
                category TEXT,
                metadata TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.commit()

    deleted: list[tuple[str, list[str] | None]] = []

    class _Vectors:
        def upsert(self, **_kwargs) -> None:
            return None

        def delete(self, collection_name: str, ids: list[str] | None = None, where=None) -> None:
            deleted.append((collection_name, ids))

    store = EpisodicMemoryStore(str(db_path), _Vectors())
    first = await store.store_episode("tui_a", "Built the gateway", "success")
    second = await store.store_episode("tui_a", "temporary note", "partial")
    other = await store.store_episode("tui_b", "Other session", "success")
    assert await store.delete_episode(second) is True
    assert await store.delete_episode(second) is False
    left = {row["id"] for row in await store.list_episodes()}
    assert left == {first, other}
    assert deleted == [("ltm_episodic", [f"episodic_{second}"])]
    assert await store.delete_episodes_for_conversation("tui_a") == 1
    remaining = await store.list_episodes()
    assert [row["source"] for row in remaining] == ["tui_b"]


async def test_confirm_forgets_one_episode_and_leaves_the_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memory = _Memory()
    memory.episodes = [
        {
            "id": 4,
            "content": "Deployed the gateway",
            "source": "tui_old",
            "created_at": "2026-03-01",
        },
        {
            "id": 9,
            "content": "Renamed the service",
            "source": "tui_old",
            "created_at": "2026-03-02",
        },
    ]
    memory.sessions = [
        {
            "conversation_id": "tui_old",
            "message_count": 12,
            "last_timestamp": "2026-03-02",
            "preview": "deploy the gateway",
        }
    ]
    _patch(monkeypatch, memory)
    bridge = _Bridge(json.dumps({"forget_0": ["m2"]}))
    tokens = subagent_scope("main", interaction_bridge=bridge)
    try:
        raw = await ReviewMemoryTool().execute(action="confirm")
    finally:
        reset_subagent_scope(tokens)
    payload = json.loads(raw)
    assert payload["forgotten"] == ["4"]
    assert "tui_old" in payload["kept"]
    assert memory.deleted_episodes == [4]
    assert memory.deleted_sessions == []
    prompt = bridge.questions[0]["prompt"]
    assert "Deployed the gateway" in prompt
    assert "Сводка #4" in prompt
    assert "сессия tui_old" in prompt
    assert "Удалится только эта сводка" in prompt
    labels = [option["label"] for option in bridge.questions[0]["options"]]
    assert any("Deployed the gateway" in label for label in labels)
    episode = next(option for option in bridge.questions[0]["options"] if option["id"] == "m2")
    assert "только эта сводка" in episode["description"]


async def test_confirm_forgets_a_session_and_its_episode_summaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.tools.execution_context import conversation_scope, reset_conversation_scope

    memory = _Memory()
    memory.sessions = [
        {
            "conversation_id": "tui_keep",
            "message_count": 3,
            "last_timestamp": "2026-04-01",
            "preview": "leave this chat",
        },
        {
            "conversation_id": "tui_old",
            "message_count": 12,
            "last_timestamp": "2026-03-02",
            "preview": "deploy the gateway",
        },
    ]
    _patch(monkeypatch, memory)
    bridge = _Bridge(json.dumps({"forget_0": ["m2"]}))
    scope = conversation_scope("tui_keep")
    tokens = subagent_scope("main", interaction_bridge=bridge)
    try:
        raw = await ReviewMemoryTool().execute(action="confirm")
    finally:
        reset_subagent_scope(tokens)
        reset_conversation_scope(scope)
    payload = json.loads(raw)
    assert payload["forgotten"] == ["tui_old"]
    assert "tui_keep" in payload["kept"]
    assert memory.deleted_sessions == ["tui_old"]
    assert memory.deleted_session_episodes == ["tui_old"]
    prompt = bridge.questions[0]["prompt"]
    assert "leave this chat" in prompt
    assert "deploy the gateway" in prompt
    assert "Диалог tui_keep, этот чат" in prompt
    assert "Удалится переписка" in prompt
    labels = [option["label"] for option in bridge.questions[0]["options"]]
    assert any("leave this chat" in label for label in labels)
    session = next(option for option in bridge.questions[0]["options"] if option["id"] == "m2")
    assert "переписка" in session["description"]


async def test_apply_deletes_named_keys_without_asking(monkeypatch: pytest.MonkeyPatch) -> None:
    memory = _Memory()
    _patch(monkeypatch, memory)
    raw = await ReviewMemoryTool().execute(action="apply", forget=["drop_me"])
    payload = json.loads(raw)
    assert payload["ok"] is True
    assert payload["forgotten"] == ["drop_me"]
    assert memory.deleted == [("semantic", "drop_me")]


async def test_apply_keeps_the_last_days_and_the_current_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import datetime, timedelta

    from core.tools.execution_context import conversation_scope, reset_conversation_scope

    old = (datetime.now() - timedelta(days=30)).isoformat(timespec="seconds")
    fresh = (datetime.now() - timedelta(days=1)).isoformat(timespec="seconds")
    memory = _Memory()
    memory.facts = [
        {"key": "old_fact", "content": "старый факт про город", "updated_at": old, "category": ""},
        {"key": "new_fact", "content": "свежий факт", "updated_at": fresh, "category": ""},
    ]
    memory.strategies = []
    memory.episodes = [
        {
            "id": 4,
            "content": "Сводка старого деплоя",
            "source": "tui_old",
            "created_at": old,
        }
    ]
    memory.sessions = [
        {
            "conversation_id": "tui_old",
            "message_count": 4,
            "last_timestamp": old,
            "preview": "деплой шлюза",
        },
        {
            "conversation_id": "tui_now",
            "message_count": 2,
            "last_timestamp": old,
            "preview": "текущий разговор",
        },
        {
            "conversation_id": "tui_fresh",
            "message_count": 1,
            "last_timestamp": fresh,
            "preview": "вчерашний вопрос",
        },
    ]
    _patch(monkeypatch, memory)
    scope = conversation_scope("tui_now")
    try:
        raw = await ReviewMemoryTool().execute(action="apply", keep_days=7)
    finally:
        reset_conversation_scope(scope)
    payload = json.loads(raw)
    assert payload["ok"] is True
    assert set(payload["forgotten"]) == {"old_fact", "4", "tui_old"}
    assert "tui_now" not in payload["forgotten"]
    assert "new_fact" not in payload["forgotten"]
    assert "tui_fresh" not in payload["forgotten"]


async def test_apply_without_a_target_deletes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    memory = _Memory()
    _patch(monkeypatch, memory)
    raw = await ReviewMemoryTool().execute(action="apply")
    payload = json.loads(raw)
    assert payload["ok"] is False
    assert payload["code"] == "nothing_to_apply"
    assert memory.deleted == []


def test_review_memory_slot_and_plan_mode() -> None:
    assert "review_memory" in CORE_TOOL_NAMES
    assert tool_allowed_for_slot("review_memory", "main")
    assert tool_allowed_for_slot("review_memory", "supervisor")
    assert not tool_allowed_for_slot("review_memory", "coder")
    assert "review_memory" in PLAN_MODE_BLOCKED
    assert is_plan_mode_blocked("review_memory")
