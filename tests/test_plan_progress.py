"""Plan-mode live progress messages (ThinkingEvent phases)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from core.graph.nodes.plan_node import _emit_plan_progress
from core.i18n.live_ui import live_plan_phase
from core.i18n.messages import t


def test_live_plan_phase_ru() -> None:
    msg = live_plan_phase("default", "phase_llm", model="smart", timeout=600)
    # Product default locale is ru
    assert "план" in msg.lower() or "plan" in msg.lower()
    assert "smart" in msg
    assert "600" in msg


def test_live_plan_phase_en_keys_exist() -> None:
    for key in (
        "phase_start",
        "phase_context",
        "phase_handbook",
        "phase_llm",
        "phase_llm_wait",
        "phase_attempt",
        "phase_received",
        "phase_quality",
        "phase_retry",
        "phase_save",
        "phase_ready",
        "phase_waiting_review",
    ):
        text = t(f"live.plan.{key}", "en", **{
            "memories": 1,
            "tools": 2,
            "path": "/tmp",
            "model": "m",
            "timeout": 30,
            "elapsed": 12,
            "attempt": 1,
            "total": 2,
            "chars": 100,
            "reason": "x",
            "steps": 3,
        })
        assert text
        assert "live.plan." not in text  # resolved, not missing-key echo


def test_emit_plan_progress_emits_thinking() -> None:
    agent = MagicMock()
    _emit_plan_progress(agent, "conv1", "default", "phase_start")
    agent.emit.assert_called_once()
    ev = agent.emit.call_args[0][0]
    assert ev.conversation_id == "conv1"
    assert "📋" in (ev.message or "") or "plan" in (ev.message or "").lower() or "план" in (
        ev.message or ""
    ).lower()


@pytest.mark.asyncio
async def test_plan_llm_heartbeat_emits_wait(monkeypatch) -> None:
    import asyncio

    from core.graph.nodes import plan_node as pn

    monkeypatch.setattr(pn, "_PLAN_LLM_HEARTBEAT_S", 0.05)
    agent = MagicMock()
    stop = asyncio.Event()
    task = asyncio.create_task(
        pn._plan_llm_heartbeat(
            stop,
            agent=agent,
            conversation_id="c",
            profile_name="default",
            timeout=600,
            t0=0.0,
        )
    )
    await asyncio.sleep(0.12)
    stop.set()
    await task
    assert agent.emit.call_count >= 1
    msgs = [c.args[0].message for c in agent.emit.call_args_list]
    assert any("600" in m for m in msgs)
