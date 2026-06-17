"""LangGraph checkpointer must work with graph.ainvoke (async)."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_async_checkpointer_sqlite_ainvoke(tmp_path) -> None:
    from core.persistence import async_checkpointer
    from langgraph.graph import END, START, StateGraph
    from typing_extensions import TypedDict

    class _State(TypedDict):
        value: int

    async def bump(state: _State) -> dict:
        return {"value": state.get("value", 0) + 1}

    graph = StateGraph(_State)
    graph.add_node("bump", bump)
    graph.add_edge(START, "bump")
    graph.add_edge("bump", END)

    db_path = tmp_path / "cp.db"
    async with async_checkpointer(use_persistent=True, db_path=str(db_path)) as cp:
        compiled = graph.compile(checkpointer=cp)
        result = await compiled.ainvoke(
            {"value": 0},
            config={"configurable": {"thread_id": "t1"}},
        )

    assert result["value"] == 1