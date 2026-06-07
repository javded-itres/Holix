"""Doctor diagnostic finding model."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


SeverityLevel = Literal["error", "warning", "info"]


@dataclass(slots=True)
class DoctorFinding:
    code: str
    severity: SeverityLevel
    title: str
    detail: str
    recommendation: str
    fix_id: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def is_error(self) -> bool:
        return self.severity == Severity.ERROR.value

    @property
    def auto_fixable(self) -> bool:
        return self.fix_id is not None