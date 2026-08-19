"""Profile-local skill hygiene achievements (not injected into the agent prompt)."""

from core.achievements.engine import AchievementStore, record_skill_signal

__all__ = ["AchievementStore", "record_skill_signal"]
