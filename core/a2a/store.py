"""In-memory A2A task store (process-local; gateway lifetime)."""

from __future__ import annotations

import threading

from core.a2a.models import A2ATask


class A2ATaskStore:
    """Thread-safe task registry for A2A server side."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tasks: dict[str, A2ATask] = {}

    def put(self, task: A2ATask) -> A2ATask:
        with self._lock:
            self._tasks[task.id] = task
            return task

    def get(self, task_id: str) -> A2ATask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def delete(self, task_id: str) -> bool:
        with self._lock:
            return self._tasks.pop(task_id, None) is not None

    def list_tasks(
        self,
        *,
        profile: str | None = None,
        context_id: str | None = None,
        limit: int = 50,
    ) -> list[A2ATask]:
        with self._lock:
            items = list(self._tasks.values())
        if profile:
            items = [t for t in items if t.profile == profile]
        if context_id:
            items = [t for t in items if t.contextId == context_id]
        items.sort(key=lambda t: t.status.timestamp, reverse=True)
        return items[: max(1, min(int(limit or 50), 100))]

    def clear(self) -> None:
        with self._lock:
            self._tasks.clear()


# Process-wide store for gateway
_default_store: A2ATaskStore | None = None
_store_lock = threading.Lock()


def get_a2a_task_store() -> A2ATaskStore:
    global _default_store
    with _store_lock:
        if _default_store is None:
            _default_store = A2ATaskStore()
        return _default_store
