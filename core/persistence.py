"""
Persistence — wraps LangGraph checkpointing for Holix.

Uses InMemorySaver for in-process checkpointing. Profile-aware
path resolution for file-based checkpointers.
"""

import logging

from langgraph.checkpoint.memory import InMemorySaver

logger = logging.getLogger(__name__)


def create_checkpointer(
    use_persistent: bool = False,
    db_path: str | None = None,
):
    """Create a checkpointer for the LangGraph.

    Args:
        use_persistent: If True, use SQLite-based checkpointing.
                       If False (default), use in-memory checkpointing.
        db_path: Path for persistent checkpoint DB. Only used
                 when use_persistent=True.

    Returns:
        A checkpointer instance compatible with LangGraph's compile().
    """
    if use_persistent and db_path:
        try:
            # Try SQLite-based checkpointing
            # Requires: pip install langgraph-checkpoint-sqlite
            import sqlite3

            from langgraph.checkpoint.sqlite import SqliteSaver

            from core.paths import prepare_sqlite_db_file

            resolved = prepare_sqlite_db_file(db_path)
            conn = sqlite3.connect(str(resolved), check_same_thread=False)
            checkpointer = SqliteSaver(conn)
            logger.info(f"Using SQLite checkpointer at {resolved}")
            return checkpointer
        except ImportError:
            logger.warning(
                "langgraph-checkpoint-sqlite not installed, "
                "falling back to InMemorySaver"
            )

    # Default: in-memory checkpointing
    checkpointer = InMemorySaver()
    logger.info("Using InMemorySaver for checkpointing")
    return checkpointer