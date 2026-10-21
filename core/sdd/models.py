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
    # Optional volume label: xs | s | m | l | xl (see core.sdd.task_sizing).
    size: str = ""
    # How a reader can tell the task is done (test, command, or observable).
    done_when: str = ""
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
    tools_presentation: str | None = None
    apply_ready: bool = False
    missing: list[str] = field(default_factory=list)
    skip_specs: bool = False
    task_warnings: list[str] = field(default_factory=list)

    @property
    def tasks_complete(self) -> bool:
        return self.tasks_total > 0 and self.tasks_done == self.tasks_total

    def to_dict(self) -> dict:
        return {
            "change_id": self.change_id,
            "path": self.path,
            "artifacts": dict(self.artifacts),
            "tasks_total": self.tasks_total,
            "tasks_done": self.tasks_done,
            "tasks_complete": self.tasks_complete,
            "assignees": dict(self.assignees),
            "apply_mode": self.apply_mode,
            "tools_presentation": self.tools_presentation,
            "apply_ready": self.apply_ready,
            "missing": list(self.missing),
            "skip_specs": self.skip_specs,
            "task_warnings": list(self.task_warnings),
        }
