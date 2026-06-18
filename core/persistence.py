"""
Persistence — wraps LangGraph checkpointing for Holix.

Uses InMemorySaver for sync/studio entry points. Async graph runs use
AsyncSqliteSaver via async_checkpointer() (required for graph.ainvoke).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

logger = logging.getLogger(__name__)


def create_checkpointer(
    use_persistent: bool = False,
    db_path: str | None = None,
):
    """Create an in-memory checkpointer (sync-safe, for Studio / tests).

    Do not use sync SqliteSaver with graph.ainvoke() — use async_checkpointer()
    for persistent SQLite checkpointing.
    """
    if use_persistent and db_path:
        logger.debug(
            "create_checkpointer(use_persistent=True) ignored — "
            "use async_checkpointer() for SQLite with ainvoke"
        )
    checkpointer = InMemorySaver()
    logger.info("Using InMemorySaver for checkpointing")
    return checkpointer


@asynccontextmanager
async def async_checkpointer(
    *,
    use_persistent: bool = False,
    db_path: str | None = None,
) -> AsyncIterator[Any]:
    """Yield a checkpointer suitable for async graph.ainvoke()."""
    if use_persistent and db_path:
        try:
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

            from core.paths import prepare_sqlite_db_file

            resolved = prepare_sqlite_db_file(db_path)
            conn_string = str(resolved)
            async with AsyncSqliteSaver.from_conn_string(conn_string) as checkpointer:
                logger.info("Using AsyncSqliteSaver at %s", resolved)
                yield checkpointer
                return
        except ImportError:
            logger.warning(
                "langgraph-checkpoint-sqlite or aiosqlite not installed, "
                "falling back to InMemorySaver"
            )
        except Exception as exc:
            logger.warning(
                "AsyncSqliteSaver failed (%s), falling back to InMemorySaver",
                exc,
            )

    yield InMemorySaver()
    logger.info("Using InMemorySaver for checkpointing")