"""Live LLM: session goal, semantic search, and a workspace write."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.live_llm, pytest.mark.llm]


def _skip_unreliable(result) -> None:
    low = result.text.lower()
    if "timed out" in low or "connection error" in low:
        pytest.skip(f"provider timeout: {result.text[:120]}")
    if result.looks_unreliable():
        pytest.skip(f"unreliable live reply: {result.text[:120]}")


@pytest.mark.asyncio
async def test_live_73_goal_search_and_write(
    live_harness,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.runtime.session_goal import get_goal

    profile_root = tmp_path / "profile-store"

    def _dir(name: str | None = None, **_kwargs: object) -> Path:
        path = profile_root / (name or "default")
        path.mkdir(parents=True, exist_ok=True)
        return path

    monkeypatch.setattr("core.profile.names.profile_dir_for_name", _dir)
    monkeypatch.setenv("HOLIX_CODE_INDEX", "1")
    monkeypatch.setenv("HOLIX_GOAL_CONTINUATIONS", "0")
    (live_harness.workspace / "auth.py").write_text(
        "def authenticate_user(name):\n    return name == 'ada'\n",
        encoding="utf-8",
    )
    result = await live_harness.run(
        "You MUST call these Holix tools, in order, and not only describe them.\n"
        "1) semantic_search with query='authenticate user'.\n"
        "2) session_goal with action='start' and objective='write the marker file'.\n"
        "3) write_file path='goal_marker.txt' content='ok'.\n"
        "4) session_goal with action='report' and status='complete' and reason='marker written'.\n"
        "Then say done.",
        conversation_id="live_73",
        timeout_s=360,
    )
    _skip_unreliable(result)
    names = result.tool_names()
    assert "semantic_search" in names, names
    assert "session_goal" in names, names
    assert "write_file" in names, names
    assert live_harness.exists("goal_marker.txt"), (live_harness.list_workspace(), result.text)
    goal = get_goal("default", "live_73")
    assert goal is not None and goal.status == "complete", goal
