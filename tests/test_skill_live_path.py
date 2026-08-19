"""End-to-end skill loop without a live provider: stage → score → notice → decide."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from core.agent_events import SkillProposedEvent
from core.di.runtime_config import HolixRuntimeConfig
from core.i18n import t
from core.plugins.hooks import notify_hooks
from core.skills.decisions import decide_skill_proposal
from core.skills.lifecycle import format_skill_notice_text, settle_proposal
from core.skills.manager import SkillsManager
from core.skills.proposal import SkillProposalStore
from core.skills.quality import score_tier
from core.skills.self_improve import maybe_propose_skill


def _mgr(tmp_path: Path) -> SkillsManager:
    return SkillsManager(
        HolixRuntimeConfig.from_settings().with_overrides(
            skills_dir=str(tmp_path / "skills"),
            vector_db_path=str(tmp_path / "vector"),
            profile_name="live-path",
        )
    )


def _rich_session() -> list[dict]:
    return [
        {"role": "user", "content": "Собери FastAPI каталог адресов с Dishka и pytest"},
        {"role": "assistant", "content": "Сначала сверюсь с доками и Impоrtами."},
        {"role": "tool", "name": "mcp_context7_resolve-library-id", "content": "fastapi"},
        {"role": "tool", "name": "mcp_context7_query-docs", "content": "APIRouter, Depends"},
        {"role": "tool", "name": "read_file", "content": "empty"},
        {"role": "tool", "name": "write_file", "content": "wrote app/main.py"},
        {"role": "tool", "name": "run_terminal_command", "content": "pytest 3 passed"},
        {"role": "assistant", "content": "Готово: CRUD и тесты зелёные."},
    ]


@pytest.mark.asyncio
async def test_live_path_low_score_notifies_and_needs_human(tmp_path: Path, monkeypatch) -> None:
    notices: list[dict] = []
    notify_hooks.skill_notice_listeners.append(notices.append)
    try:
        mgr = _mgr(tmp_path)
        agent = MagicMock()
        agent.skills = mgr
        agent.model = "coder"
        agent.client = MagicMock()
        agent.agent_slot = "main"
        agent.profile_name = "live-path"
        agent.config = MagicMock(profile_name="live-path")
        agent.emit = MagicMock()
        agent.run_id = "run-live-1"

        async def _yes(_messages, _result):
            return True

        mgr.should_create_skill = _yes  # type: ignore[method-assign]
        fake = {
            "action": "create",
            "name": "fastapi-dishka-catalog",
            "description": "Каталог FastAPI с Dishka",
            "tags": ["fastapi"],
            "content": "## When to Use\nCRUD\n\n## Procedure\n1. Context7\n2. write_file\n",
            "examples": [],
            "refuse_reason": "",
            "quality_score": 42,
        }
        gen = MagicMock()
        gen.create_skill_from_session = pytest.importorskip("unittest.mock").AsyncMock(
            return_value=fake
        )
        from unittest.mock import AsyncMock
        from unittest.mock import MagicMock as MM

        gen.create_skill_from_session = AsyncMock(return_value=fake)
        monkeypatch.setattr("core.skills.generator.SkillGenerator", MM(return_value=gen))

        rec = await maybe_propose_skill(
            agent, "conv-live", _rich_session(), "Готово: CRUD и тесты зелёные."
        )
        assert rec is not None
        assert rec.get("auto_applied") is False
        assert rec.get("quality_score") == 42
        assert rec.get("tier", {}).get("id") == "silver"
        assert not (mgr.skills_dir / "fastapi-dishka-catalog.md").exists()
        store_pending = SkillProposalStore(mgr.skills_dir).list_pending()
        assert store_pending
        assert store_pending[0]["name"] == "fastapi-dishka-catalog"

        assert notices, "expected a messenger/UI notice"
        payload = notices[-1]
        assert payload["auto_applied"] is False
        assert payload["quality_score"] == 42
        proposed = [
            c.args[0]
            for c in agent.emit.call_args_list
            if c.args and isinstance(c.args[0], SkillProposedEvent)
        ]
        assert proposed
        assert proposed[-1].quality_score == 42
        assert "quality_score" in proposed[-1].to_dict()
        assert payload["settings_path"].endswith("sub=skills")
        ru = format_skill_notice_text({**payload, "locale": "ru"})
        assert "Предложен новый skill" in ru
        assert "42/100" in ru
        assert "Серебро" in ru or "серебр" in ru.lower()

        # Isolate approve from the default profile's Chroma (embedder conflict).
        monkeypatch.setattr(
            "core.skills.decisions.manager_for_profile",
            lambda _profile: mgr,
        )
        decided = decide_skill_proposal(
            "live-path",
            rec["id"],
            approve=True,
            locale="ru",
        )
        assert decided["ok"] is True
        assert (mgr.skills_dir / "fastapi-dishka-catalog.md").is_file()
        assert SkillProposalStore(mgr.skills_dir).list_pending() == []
    finally:
        notify_hooks.skill_notice_listeners[:] = [
            fn for fn in notify_hooks.skill_notice_listeners if fn is not notices.append
        ]


@pytest.mark.asyncio
async def test_live_path_gold_auto_approves_and_still_notifies(tmp_path: Path, monkeypatch) -> None:
    notices: list[dict] = []
    notify_hooks.skill_notice_listeners.append(notices.append)
    try:
        mgr = _mgr(tmp_path)
        agent = MagicMock()
        agent.skills = mgr
        agent.model = "coder"
        agent.client = MagicMock()
        agent.agent_slot = "main"
        agent.profile_name = "live-path"
        agent.config = MagicMock(profile_name="live-path")
        agent.emit = MagicMock()

        async def _yes(_messages, _result):
            return True

        mgr.should_create_skill = _yes  # type: ignore[method-assign]
        fake = {
            "action": "create",
            "name": "gold-deploy-runbook",
            "description": "Как выкатываем staging",
            "tags": ["deploy"],
            "content": "## Procedure\n1. build\n2. rsync\n3. healthcheck\n",
            "examples": [],
            "refuse_reason": "",
            "quality_score": 74,
        }
        from unittest.mock import AsyncMock
        from unittest.mock import MagicMock as MM

        gen = MM()
        gen.create_skill_from_session = AsyncMock(return_value=fake)
        monkeypatch.setattr("core.skills.generator.SkillGenerator", MM(return_value=gen))

        rec = await maybe_propose_skill(
            agent, "conv-gold", _rich_session(), "Готово: задеплоили staging."
        )
        assert rec is not None
        assert rec.get("auto_applied") is True
        assert rec.get("tier", {}).get("id") == "gold"
        assert (mgr.skills_dir / "gold-deploy-runbook.md").is_file()
        assert SkillProposalStore(mgr.skills_dir).list_pending() == []
        assert notices and notices[-1]["auto_applied"] is True
        text = format_skill_notice_text({**notices[-1], "locale": "ru"})
        assert "принят автоматически" in text
        assert "74/100" in text
        # Auto-applied notices must not require a human click.
        assert "Примите или отклоните" not in text
        emitted = [c.args[0] for c in agent.emit.call_args_list]
        assert any(isinstance(e, SkillProposedEvent) for e in emitted)
    finally:
        notify_hooks.skill_notice_listeners[:] = [
            fn for fn in notify_hooks.skill_notice_listeners if fn is not notices.append
        ]


def test_live_path_human_reject_via_suffix(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    store = SkillProposalStore(mgr.skills_dir)
    rec = store.stage(
        name="bronze-flow",
        action="create",
        content="thin",
        description="слабо",
        quality_score=28,
        locale="ru",
    )
    settle_proposal(store, rec, manager=mgr, profile="live-path")
    pending = store.list_pending()
    assert pending
    suffix = str(pending[0]["id"])[-8:]
    hit = store.get(pending[0]["id"])
    assert hit
    store.reject(hit["id"], reason="user")
    assert store.list_pending() == []
    assert not (mgr.skills_dir / "bronze-flow.md").exists()
    assert suffix
    assert score_tier(28)["label_ru"] == "Бронза"
    assert "Отклонить" in t("skill.btn.reject", "ru")
