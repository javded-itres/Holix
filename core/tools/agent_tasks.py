"""List and stop the current agent's background tasks."""

from __future__ import annotations

from core.tools.base import BaseTool


class ListAgentTasksTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "list_agent_tasks"
        self.description = (
            "List background tasks in this chat (running and recently finished): "
            "shell jobs and image/video generation. Not sub-agents. "
            "Call this when the user asks what is running. Quote only ids from "
            "this result. Do not poll; you are notified when a task finishes."
        )
        self.risk_level = "low"
        self.parameters = {"type": "object", "properties": {}, "required": []}

    async def execute(self) -> str:
        from core.runtime.agent_tasks import get_agent_task_registry
        from core.tools.execution_context import get_conversation_id, get_profile_name

        return get_agent_task_registry().format_list(
            profile=get_profile_name() or "default",
            conversation_id=get_conversation_id() or "default",
        )


class StopAgentTaskTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "stop_agent_task"
        self.description = (
            "Stop one background task started with run_terminal_command background=true. "
            "Not for persistent servers (use stop_background_process) and not for sub-agents."
        )
        self.risk_level = "medium"
        self.parameters = {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Id returned when the task was started (task_…).",
                },
            },
            "required": ["task_id"],
        }

    async def execute(self, task_id: str) -> str:
        from core.runtime.agent_tasks import get_agent_task_registry

        return await get_agent_task_registry().stop(task_id)


def register_agent_task_tools(registry) -> None:
    registry.register(ListAgentTasksTool())
    registry.register(StopAgentTaskTool())
