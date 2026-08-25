"""LangGraph checkpointer must work with graph.ainvoke (async)."""

from __future__ import annotations

import asyncio

import pytest
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict


class _State(TypedDict):
    value: int


def _bump_graph():
    graph = StateGraph(_State)

    async def bump(state: _State) -> dict:
        return {"value": state.get("value", 0) + 1}

    graph.add_node("bump", bump)
    graph.add_edge(START, "bump")
    graph.add_edge("bump", END)
    return graph


@pytest.mark.asyncio
async def test_async_checkpointer_sqlite_ainvoke(tmp_path) -> None:
    from core.persistence import async_checkpointer

    db_path = tmp_path / "cp.db"
    async with async_checkpointer(use_persistent=True, db_path=str(db_path)) as cp:
        compiled = _bump_graph().compile(checkpointer=cp)
        result = await compiled.ainvoke(
            {"value": 0},
            config={"configurable": {"thread_id": "t1"}},
        )

    assert result["value"] == 1


@pytest.mark.asyncio
async def test_overlapping_checkpointers_share_saver(tmp_path) -> None:
    from core.persistence import async_checkpointer

    db_path = tmp_path / "shared.db"
    async with async_checkpointer(use_persistent=True, db_path=str(db_path)) as outer:
        async with async_checkpointer(use_persistent=True, db_path=str(db_path)) as inner:
            assert outer is inner


@pytest.mark.asyncio
async def test_concurrent_ainvoke_same_checkpoint_db(tmp_path) -> None:
    from core.persistence import async_checkpointer

    db_path = tmp_path / "race.db"

    async def run(thread_id: str) -> int:
        async with async_checkpointer(use_persistent=True, db_path=str(db_path)) as cp:
            compiled = _bump_graph().compile(checkpointer=cp)
            result = await compiled.ainvoke(
                {"value": 0},
                config={"configurable": {"thread_id": thread_id}},
            )
        return int(result["value"])

    values = await asyncio.gather(*(run(f"t{i}") for i in range(8)))
    assert values == [1] * 8


@pytest.mark.asyncio
async def test_graph_error_is_not_swallowed_by_checkpointer(tmp_path) -> None:
    from core.persistence import async_checkpointer

    graph = StateGraph(_State)

    async def boom(_state: _State) -> dict:
        raise RuntimeError("graph-boom")

    graph.add_node("boom", boom)
    graph.add_edge(START, "boom")
    graph.add_edge("boom", END)

    db_path = tmp_path / "boom.db"
    async with async_checkpointer(use_persistent=True, db_path=str(db_path)) as cp:
        compiled = graph.compile(checkpointer=cp)
        with pytest.raises(RuntimeError, match="graph-boom"):
            await compiled.ainvoke(
                {"value": 0},
                config={"configurable": {"thread_id": "t-boom"}},
            )


def test_subagent_runtime_clears_checkpoint_path() -> None:
    from core.di.runtime_config import HolixRuntimeConfig

    parent = HolixRuntimeConfig.from_settings().with_overrides(
        langgraph_checkpoint_db_path="/tmp/holix-checkpoints.db",
    )
    child = parent.with_overrides(langgraph_checkpoint_db_path="")
    assert parent.langgraph_checkpoint_db_path.endswith("checkpoints.db")
    assert child.langgraph_checkpoint_db_path == ""
    assert not (getattr(child, "use_langgraph", True) and child.langgraph_checkpoint_db_path)
