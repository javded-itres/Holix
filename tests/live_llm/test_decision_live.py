"""Live System One checks against a configured decision model.

Skipped unless ``HOLIX_DECISION_LIVE=1``. Default CI uses ``-m "not llm"``.
The API key is read from the environment or the local profile ``.env`` and is
not printed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from core.decision.config import resolve_decision
from core.decision.gates import choice_label, noul_value
from core.decision.internal import (
    draft_should_continue,
    promote_skill,
    reflexion_assessment,
    shell_auto_allow,
)
from core.decision.systemone import call_systemone, probe_decision

pytestmark = pytest.mark.live_llm


def _live_enabled() -> bool:
    return os.environ.get("HOLIX_DECISION_LIVE", "").strip().lower() in {"1", "true", "yes"}


def _read_key() -> str:
    for name in ("HOLIX_DECISION_API_KEY", "DECISION_API_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    path = Path.home() / ".holix" / "profiles" / "default" / ".env"
    if not path.is_file():
        return ""
    found = ""
    for line in path.read_text(errors="replace").splitlines():
        if line.startswith("DECISION_API_KEY=") or line.startswith("MIKROLLM_API_KEY="):
            found = line.split("=", 1)[1].strip().strip("\"'")
            if line.startswith("DECISION_API_KEY="):
                return found
    return found


def _block() -> dict:
    return {
        "enabled": True,
        "preset": "custom",
        "base_url": os.environ.get("HOLIX_DECISION_BASE_URL", "http://192.168.88.1:4000").rstrip(
            "/"
        ),
        "model": os.environ.get("HOLIX_DECISION_MODEL", "nimble"),
        "timeout_s": 90,
        "internal": {
            "reflexion": True,
            "is_final": True,
            "skill_choice": True,
            "shell_allow": True,
        },
        "thresholds": {"noul": 0.8, "confidence": 0.0, "quality": 0.7},
    }


def _agent(block: dict):
    return SimpleNamespace(config=SimpleNamespace(decision=block))


@pytest.fixture
def decision_agent(monkeypatch: pytest.MonkeyPatch):
    if not _live_enabled():
        pytest.skip("HOLIX_DECISION_LIVE is not set")
    key = _read_key()
    if not key:
        pytest.skip("no decision API key")
    monkeypatch.setenv("DECISION_API_KEY", key)
    block = _block()
    return _agent(block), resolve_decision(block)


def _payload(text: str) -> dict:
    assert not text.startswith("System One error:"), text
    parsed = json.loads(text)
    assert isinstance(parsed, dict)
    return parsed


async def test_live_decision_probe(decision_agent) -> None:
    _agent_obj, resolved = decision_agent
    assert await probe_decision(resolved) == "ok"


async def test_live_decision_noul_separates_yes_and_no(decision_agent) -> None:
    _agent_obj, resolved = decision_agent
    yes = await call_systemone(
        resolved,
        "Москва — столица России.",
        {"fact": {"type": "noul", "instructions": "Это утверждение верно."}},
    )
    no = await call_systemone(
        resolved,
        "Москва — столица Франции.",
        {"fact": {"type": "noul", "instructions": "Это утверждение верно."}},
    )
    yes_noul = noul_value(_payload(yes), "fact")
    no_noul = noul_value(_payload(no), "fact")
    assert yes_noul is not None and no_noul is not None
    assert yes_noul >= 0.8
    assert no_noul <= 0.2


async def test_live_decision_choice_stays_in_the_allowed_set(decision_agent) -> None:
    _agent_obj, resolved = decision_agent
    text = await call_systemone(
        resolved,
        "Списали оплату дважды. Нужен возврат.",
        {
            "team": {
                "type": "choice",
                "instructions": "Какая команда должна взять тикет?",
                "criteria": {
                    "billing": "оплаты и возвраты",
                    "technical": "ошибки программы",
                },
            }
        },
    )
    label = choice_label(
        _payload(text),
        "team",
        {"billing", "technical"},
        confidence_threshold=0.0,
    )
    assert label == "billing"


async def test_live_decision_score_ranks_a_complete_draft_higher(decision_agent) -> None:
    agent, _resolved = decision_agent
    task = "Сколько будет 2+2? Ответь одним числом."
    good = await reflexion_assessment(agent, task, "4")
    bad = await reflexion_assessment(agent, task, "Я подумаю об этом позже и ничего не посчитаю.")
    assert good is not None and bad is not None
    assert good.quality_score >= 2 / 3
    assert bad.quality_score <= 1 / 3
    assert bad.needs_refinement is True


async def test_live_decision_end_of_turn_holds_only_an_incomplete_draft(decision_agent) -> None:
    agent, _resolved = decision_agent
    task = "Назови столицу России одним словом."
    assert await draft_should_continue(agent, task, "Москва") is False
    assert await draft_should_continue(agent, task, "Сейчас поищу и потом отвечу.") is True


def test_live_decision_skill_choice_promotes_a_match(decision_agent) -> None:
    agent, _resolved = decision_agent
    picked = promote_skill(
        agent,
        "покажи статус git",
        ["git", "docker"],
        {"git": "статус и коммиты репозитория", "docker": "контейнеры и образы"},
    )
    assert picked == "git"


async def test_live_decision_shell_allow_rejects_a_dangerous_command(decision_agent) -> None:
    agent, _resolved = decision_agent
    assert await shell_auto_allow(agent, "pwd") is True
    assert await shell_auto_allow(agent, "rm -rf /") is False


async def test_live_decision_tool_returns_json(
    decision_agent, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent, _resolved = decision_agent
    block = agent.config.decision

    class _Profiles:
        def load_profile(self, name: str):
            del name
            return SimpleNamespace(decision=block)

    monkeypatch.setattr("core.profile.service.ProfileManager", _Profiles)
    monkeypatch.setattr("core.tools.execution_context.get_profile_name", lambda: "live-decision")
    from core.tools.systemone import SystemOneDecideTool

    text = await SystemOneDecideTool().execute(
        state="проверка",
        questions={"probe": {"type": "noul", "instructions": "Это короткое служебное сообщение"}},
    )
    assert noul_value(_payload(text), "probe") is not None
