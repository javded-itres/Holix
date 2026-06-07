"""SkillGenerator uses the agent model, not global settings."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.skills.generator import SkillGenerator


@pytest.mark.asyncio
async def test_skill_generator_uses_agent_model():
    client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content="SKILL_NAME: demo\nDESCRIPTION: d\nTAGS: t\nCONTENT:\nbody\n"))]
    client.chat.completions.create = AsyncMock(return_value=response)

    gen = SkillGenerator(client, model="coder")
    await gen.create_skill_from_session(
        [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "done"}],
        "do task",
    )

    assert client.chat.completions.create.await_args.kwargs["model"] == "coder"


def test_skill_generator_requires_model():
    with pytest.raises(ValueError, match="requires an active agent model"):
        SkillGenerator(MagicMock(), model="")