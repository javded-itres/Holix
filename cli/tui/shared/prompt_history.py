"""Recent user prompt history for TUI input recall."""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_PROMPT_HISTORY_LIMIT = 5


@dataclass
class PromptHistoryStore:
    """Ring of recent user-typed prompts (newest first)."""

    entries: list[str] = field(default_factory=list)
    limit: int = DEFAULT_PROMPT_HISTORY_LIMIT

    def record(self, message: str) -> None:
        text = (message or "").strip()
        if not text:
            return
        self.entries = [text] + [e for e in self.entries if e != text]
        self.entries = self.entries[: self.limit]

    def recent(self) -> list[str]:
        return list(self.entries)

    def load(self, items: list[str] | None) -> None:
        if not items:
            self.entries = []
            return
        cleaned = []
        for item in items:
            if isinstance(item, str) and (t := item.strip()):
                cleaned.append(t)
        self.entries = cleaned[: self.limit]

    def dump(self) -> list[str]:
        return list(self.entries)