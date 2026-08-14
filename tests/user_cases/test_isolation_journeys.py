"""P2 isolation: two profiles do not share conversation memory."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.user_cases.harness import UserCaseHarness
from tests.user_cases.scripted_llm import Final


@pytest.mark.user_case
@pytest.mark.integration
@pytest.mark.asyncio
async def test_uc23_two_profiles_do_not_share_memory(temp_dir, monkeypatch: pytest.MonkeyPatch):
    """UC-23: alice secret stays out of bob's conversation DB (same conversation_id)."""
    root = Path(temp_dir)
    alice = UserCaseHarness(
        root / "alice",
        monkeypatch,
        config_overrides={"profile_name": "alice"},
    )
    bob = UserCaseHarness(
        root / "bob",
        monkeypatch,
        config_overrides={"profile_name": "bob"},
    )
    await alice.setup()
    await bob.setup()
    try:
        # Distinct storage + workspaces
        assert alice.config.memory_db_path != bob.config.memory_db_path
        assert alice.config.workspace_root != bob.config.workspace_root

        alice.script([Final("I'll remember ZEBRA-ALICE-SECRET for you.")])
        r_a = await alice.run(
            "Remember the code is ZEBRA-ALICE-SECRET",
            conversation_id="shared_name",
        )
        r_a.assert_final_contains("ZEBRA-ALICE-SECRET")

        bob.script([Final("I have no prior secrets in this session.")])
        r_b = await bob.run(
            "What is the secret code?",
            conversation_id="shared_name",
        )
        r_b.assert_no_error_events()

        assert alice.agent is not None and bob.agent is not None
        alice_hist = await alice.agent.memory.get_conversation("shared_name", limit=50)
        bob_hist = await bob.agent.memory.get_conversation("shared_name", limit=50)

        alice_text = " ".join(str(m.get("content") or "") for m in alice_hist)
        bob_text = " ".join(str(m.get("content") or "") for m in bob_hist)

        assert "ZEBRA-ALICE-SECRET" in alice_text
        assert "ZEBRA-ALICE-SECRET" not in bob_text
        # Bob has his own user turn only
        assert "What is the secret code?" in bob_text
        assert "Remember the code is ZEBRA-ALICE-SECRET" not in bob_text
    finally:
        await alice.close()
        await bob.close()
