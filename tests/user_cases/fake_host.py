"""Minimal AgentHost double for slash-command surface user cases."""

from __future__ import annotations

from typing import Any


class FakeAgentHost:
    """Satisfies :class:`cli.shared.agent_host.AgentHost` for ``AgentCommands``."""

    def __init__(
        self,
        *,
        agent: Any = None,
        profile: str = "default",
        conversation_id: str = "user_case",
        execution_modes: list[str] | None = None,
        execution_mode_index: int = 0,
    ) -> None:
        self.agent = agent
        self.profile = profile
        self.conversation_id = conversation_id
        self.streaming_enabled = False
        self._execution_modes = execution_modes or [
            "react",
            "plan_and_execute",
            "hybrid",
            "auto",
        ]
        self._execution_mode_index = execution_mode_index
        self.transcript: list[str] = []
        self.workers: list[Any] = []
        self.status_refreshes = 0
        self.cleared = False

    def transcript_write(self, content: Any) -> None:
        self.transcript.append(str(content))

    def run_worker(self, work: Any, **kwargs: Any) -> None:
        self.workers.append(work)

    def _refresh_status_bar(self) -> None:
        self.status_refreshes += 1

    def action_clear_chat(self) -> None:
        self.cleared = True

    def action_help(self) -> None:
        self.transcript_write("help")

    def action_copy_output(self) -> None:
        pass

    def action_open_transcript(self) -> None:
        pass

    def copy_text(self, text: str, *, label: str = "copied") -> None:
        pass

    async def action_cycle_execution_mode(self, just_set: bool = False) -> None:
        if not just_set:
            self._execution_mode_index = (self._execution_mode_index + 1) % len(
                self._execution_modes
            )
        mode = self._execution_modes[self._execution_mode_index]
        self.transcript_write(f"mode → {mode}")

    def _action_stop_all(self) -> None:
        pass

    def _create_new_session(self) -> Any:
        return None

    def _show_sessions_list(self) -> Any:
        return None

    def _switch_to_session(self, index: int) -> Any:
        return None

    def _rename_current_session(self, name: str) -> None:
        pass

    def _get_available_profiles(self) -> list[str]:
        return [self.profile]

    def _switch_profile(self, new_profile: str, *, profile_key: str | None = None) -> Any:
        self.profile = new_profile

    def _search_memory(self, query: str) -> Any:
        return None

    def _show_full_tool_result(self, index_from_end: int = 0) -> None:
        pass

    def _list_recent_tools(self) -> None:
        pass

    def _resolve_confirmation(self, choice: Any) -> None:
        pass

    def _resolve_plan_review(self, choice: Any, feedback: str = "") -> None:
        pass

    @property
    def current_mode(self) -> str:
        return self._execution_modes[self._execution_mode_index]

    def transcript_text(self) -> str:
        return "\n".join(self.transcript)
