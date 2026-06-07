"""Backward-compatible memory module exports.

Prefer ``MemoryFacade`` for new code. ``LongTermMemoryManager`` and
``MemoryManager`` are aliases kept for existing imports.
"""

from core.memory.facade import MemoryFacade

# Aliases for backward compatibility
LongTermMemoryManager = MemoryFacade
MemoryManager = MemoryFacade

__all__ = [
    "MemoryFacade",
    "LongTermMemoryManager",
    "MemoryManager",
]