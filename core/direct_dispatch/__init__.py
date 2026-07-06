"""Fast-path dispatch for clear user intents."""

from core.direct_dispatch.intent import (
    is_status_request,
    is_subagent_list_request,
    is_work_activity_request,
)
from core.direct_dispatch.search_intent import extract_search_topic, is_web_research_request
from core.direct_dispatch.web_research import try_web_research_subagent_dispatch
from core.direct_dispatch.work_status import build_work_status_reply, should_answer_work_status

__all__ = [
    "build_work_status_reply",
    "extract_search_topic",
    "is_status_request",
    "is_subagent_list_request",
    "is_web_research_request",
    "is_work_activity_request",
    "should_answer_work_status",
    "try_web_research_subagent_dispatch",
]