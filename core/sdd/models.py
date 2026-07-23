"""SDD data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ArtifactName = Literal["proposal", "design", "tasks", "specs"]


@dataclass
class SpecTask:
    """One checklist item from ``tasks.md``."""

    id: str
    text: str
    done: bool = False
    assignee: str = "unassigned"
    reason: str = ""
    depends_on: list[str] = field(default_factory=list)
    line_index: int = -1  # index of the ``- [ ]`` line in the source (0-based)


@dataclass
class ChangeStatus:
    change_id: str
    path: str
    artifacts: dict[str, bool] = field(default_factory=dict)
    tasks_total: int = 0
    tasks_done: int = 0
    assignees: dict[str, int] = field(default_factory=dict)
    apply_mode: str | None = None
    apply_ready: bool = False
    missing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "change_id": self.change_id,
            "path": self.path,
            "artifacts": dict(self.artifacts),
            "tasks_total": self.tasks_total,
            "tasks_done": self.tasks_done,
            "assignees": dict(self.assignees),
            "apply_mode": self.apply_mode,
            "apply_ready": self.apply_ready,
            "missing": list(self.missing),
        }
