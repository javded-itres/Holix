"""Internal System One gates stay off until each flag is set."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from core.decision.config import configure_decision
from core.decision.gates import choice_label, quality_from_score
from core.decision.internal import (
    draft_should_continue,
    flag_enabled,
    hold_incomplete_draft,
    promote_skill,
    reflexion_assessment,
    set_internal_flag,
    shell_auto_allow,
)


def _agent(**decision):
    base = {
        "enabled": True,
        "preset": "nimble",
        "base_url": "http://127.0.0.1:11434",
        "model": "nimble",
    }
    base.update(decision)
    return SimpleNamespace(config=SimpleNamespace(decision=base))


def test_preset_alone_does_not_enable_internal_gates():
    raw = configure_decision({}, "nimble")
    assert flag_enabled(raw, "reflexion") is False
    assert flag_enabled(raw, "shell_allow") is False
    kept = configure_decision(
        {"preset": "nimble", "internal": {"reflexion": True}, "thresholds": {"noul": 0.9}},
        "jev",
    )
    assert kept["internal"]["reflexion"] is True
    assert kept["thresholds"]["noul"] == 0.9
    assert kept["model"] == "jev-latest"


def test_score_maps_position_and_ignores_low_confidence():
    levels_payload = {"quality": {"score": 3, "confidence": 0.95}}
    quality, needs, _level = quality_from_score(levels_payload)
    assert quality == 1.0
    assert needs is False
    low = {"quality": {"score": 1, "confidence": 0.2}}
    assert quality_from_score(low) is None
    assert (
        choice_label(
            {"skill": {"choice": "git", "confidence": 0.9}},
            "skill",
            {"git", "docker"},
        )
        == "git"
    )
    assert (
        choice_label(
            {"skill": {"choice": "git", "confidence": 0.2}},
            "skill",
            {"git"},
        )
        is None
    )


def test_reflexion_uses_score_and_falls_open_when_off(monkeypatch):
    async def fake(resolved, state, questions, post=None):
        del resolved, post
        assert questions["quality"]["criteria"][0]
        assert "задача" in state
        return json.dumps({"quality": {"score": 1, "confidence": 0.9}})

    monkeypatch.setattr("core.decision.internal.call_systemone", fake)
    scored = asyncio.run(
        reflexion_assessment(_agent(internal={"reflexion": True}), "задача", "черновик")
    )
    assert scored is not None
    assert scored.needs_refinement is True
    assert scored.reasoning == "systemone score"

    async def boom(*_args, **_kwargs):
        raise AssertionError("should not call")

    monkeypatch.setattr("core.decision.internal.call_systemone", boom)
    assert asyncio.run(reflexion_assessment(_agent(), "задача", "черновик")) is None


def test_incomplete_draft_holds_once(monkeypatch):
    async def low(resolved, state, questions, post=None):
        del resolved, state, questions, post
        return json.dumps({"complete": {"noul": 0.2}})

    monkeypatch.setattr("core.decision.internal.call_systemone", low)
    agent = _agent(internal={"is_final": True})
    assert asyncio.run(draft_should_continue(agent, "задача", "черновик")) is True
    held = asyncio.run(
        hold_incomplete_draft(
            {"user_input": "задача"},
            agent,
            [{"role": "assistant", "content": "черновик"}],
            1,
            "черновик",
        )
    )
    assert held["is_final"] is False
    assert held["decision_final_nudges"] == 1
    again = asyncio.run(
        hold_incomplete_draft(
            {"user_input": "задача", "decision_final_nudges": 1},
            agent,
            [],
            2,
            "черновик",
        )
    )
    assert again is None
    capped = asyncio.run(
        hold_incomplete_draft(
            {"user_input": "задача", "max_steps": 2},
            agent,
            [],
            2,
            "черновик",
        )
    )
    assert capped is None

    async def high(resolved, state, questions, post=None):
        del resolved, state, questions, post
        return json.dumps({"complete": {"noul": 0.95}})

    monkeypatch.setattr("core.decision.internal.call_systemone", high)
    assert asyncio.run(draft_should_continue(agent, "задача", "черновик")) is False

    async def broken(resolved, state, questions, post=None):
        del resolved, state, questions, post
        return "System One error: connection failed."

    monkeypatch.setattr("core.decision.internal.call_systemone", broken)
    assert asyncio.run(draft_should_continue(agent, "задача", "черновик")) is False


def test_shell_allow_fails_closed(monkeypatch):
    async def answer(resolved, state, questions, post=None):
        del resolved, questions, post
        value = 0.95 if "ls" in state else 0.1
        return json.dumps({"allow": {"noul": value}})

    monkeypatch.setattr("core.decision.internal.call_systemone", answer)
    agent = _agent(internal={"shell_allow": True})
    assert asyncio.run(shell_auto_allow(agent, "ls")) is True
    assert asyncio.run(shell_auto_allow(agent, "rm -rf /")) is False

    async def broken(resolved, state, questions, post=None):
        del resolved, state, questions, post
        return "System One error: timed out."

    monkeypatch.setattr("core.decision.internal.call_systemone", broken)
    assert asyncio.run(shell_auto_allow(agent, "ls")) is False
    assert asyncio.run(shell_auto_allow(_agent(), "ls")) is False


def test_skill_choice_promotes_one_candidate(monkeypatch):
    def fake(resolved, state, questions, post=None):
        del resolved, post
        assert "найди" in state
        assert set(questions["skill"]["criteria"]) == {"git", "docker"}
        return json.dumps({"skill": {"choice": "docker", "confidence": 0.91}})

    monkeypatch.setattr("core.decision.internal.call_systemone_blocking", fake)
    agent = _agent(internal={"skill_choice": True})
    assert promote_skill(agent, "найди", ["git", "docker"], {"git": "a", "docker": "b"}) == "docker"
    assert promote_skill(agent, "найди", ["git"], {"git": "a"}) is None
    assert promote_skill(_agent(), "найди", ["git", "docker"], {}) is None


def test_internal_flag_requires_a_preset():
    try:
        set_internal_flag({}, "reflexion", True)
        raised = False
    except ValueError:
        raised = True
    assert raised
    block = set_internal_flag(configure_decision({}, "nimble"), "is_final", True)
    assert block["internal"]["is_final"] is True
