"""Fast-path dispatch for clear user intents."""

from core.direct_dispatch.intent import (
    is_status_request,
    is_subagent_list_request,
    is_work_activity_request,
)
from core.direct_dispatch.work_status import build_work_status_reply, should_answer_work_status

__all__ = [
    "build_work_status_reply",
    "is_status_request",
    "is_subagent_list_request",
    "is_work_activity_request",
    "should_answer_work_status",
]