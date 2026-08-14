"""Live LLM: basic Q&A and multi-turn memory."""

from __future__ import annotations

import pytest

from tests.live_llm.provider import soft_contains

pytestmark = [pytest.mark.live_llm, pytest.mark.llm]


@pytest.mark.asyncio
async def test_live_01_simple_arithmetic(live_harness):
    r = await live_harness.run(
        "Calculate 17 + 25. "
        "You may use the calculate/math tool if available. "
        "Final answer must include the number 42 clearly in the reply text.",
        conversation_id="live_01",
        timeout_s=360,
        retries=2,
    )
    assert soft_contains(r.text, "42"), f"expected 42 in answer, got: {r.text!r}"


@pytest.mark.asyncio
async def test_live_02_world_knowledge(live_harness):
    r = await live_harness.run(
        "What is the capital of France? One short sentence.",
        conversation_id="live_02",
        timeout_s=240,
    )
    assert soft_contains(r.text, "paris", "париж"), f"expected Paris/Париж, got: {r.text!r}"


@pytest.mark.asyncio
async def test_live_03_russian_instruction(live_harness):
    r = await live_harness.run(
        "Ответь одним коротким предложением по-русски: какой цвет у неба днём в ясную погоду?",
        conversation_id="live_03",
        timeout_s=240,
    )
    assert soft_contains(r.text, "син", "голуб", "blue", min_hits=1), r.text


@pytest.mark.asyncio
async def test_live_04_multi_turn_memory(live_harness):
    r1 = await live_harness.run(
        "Remember this secret code for this chat: LIVE-ORANGE-77. Confirm briefly.",
        conversation_id="live_04",
        timeout_s=240,
    )
    assert r1.text.strip(), "empty first turn"

    r2 = await live_harness.run(
        "What secret code did I ask you to remember? Reply with the code.",
        conversation_id="live_04",
        timeout_s=240,
    )
    assert soft_contains(r2.text, "LIVE-ORANGE-77", "ORANGE", "77", min_hits=1), r2.text


@pytest.mark.asyncio
async def test_live_05_follow_format(live_harness):
    r = await live_harness.run(
        "Output a JSON object with keys name and value. "
        'name must be "holix-live", value must be 1. No markdown fences.',
        conversation_id="live_05",
        timeout_s=240,
    )
    assert soft_contains(r.text, "holix-live", min_hits=1), r.text
    assert "1" in r.text
