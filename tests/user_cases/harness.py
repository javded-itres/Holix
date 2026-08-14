"""UserCaseHarness — isolated agent journey with ScriptedLLM + real tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.agent import HolixAgent
from core.agent_events import AgentEvent
from core.di.runtime_config import HolixRuntimeConfig
from core.persistence import create_checkpointer
from core.security.confirmation import ConfirmationChoice
from core.security.confirmation_events import ConfirmationRequestEvent

from tests.factories import make_runtime_config
from tests.user_cases.assertions import JourneyResult, collect_final_text
from tests.user_cases.scripted_llm import ScriptedLLM, Turn


class Workspace:
    """Seed and inspect files under the harness workspace root."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, relative: str, content: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def read(self, relative: str) -> str:
        return (self.root / relative).read_text(encoding="utf-8")

    def exists(self, relative: str) -> bool:
        return (self.root / relative).exists()

    def path(self, relative: str = "") -> Path:
        return self.root / relative if relative else self.root


class UserCaseHarness:
    """Run product journeys: ``agent.run`` + real tools + scripted LLM.

    Default policy is unattended-style: high auto-allow, no plan review,
    meta/reflexion/subagents/MCP/browser off for determinism.

    For interactive risk flows set ``auto_allow_threshold`` below the tool risk
    (e.g. ``"medium"`` so HIGH terminal needs confirm) and call
    :meth:`auto_confirm` with ``ALLOW_ONCE`` / ``DENY``.
    """

    def __init__(
        self,
        temp_dir: str | Path,
        monkeypatch: Any,
        *,
        config_overrides: dict[str, Any] | None = None,
    ) -> None:
        self.temp_dir = Path(temp_dir)
        self.monkeypatch = monkeypatch
        self.workspace = Workspace(self.temp_dir / "workspace")
        self.data_dir = self.temp_dir / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "security").mkdir(parents=True, exist_ok=True)

        monkeypatch.setenv("HOLIX_AGENT_EXTENSIONS_OFF", "1")

        overrides: dict[str, Any] = {
            "data_dir": str(self.data_dir),
            "enable_long_term_memory": False,
            "use_langgraph": True,
            "execution_mode": "react",
            "auto_allow_threshold": "high",
            "non_interactive": False,
            "confirmation_timeout": 5,
            "plan_review_enabled": False,
            "enable_meta_agent": False,
            "enable_self_refinement": False,
            "enable_subagents": False,
            "enable_browser_tools": False,
            "mcp_enabled": False,
            "self_extensions_enabled": False,
            "max_steps": 12,
            "workspace_root": str(self.workspace.root),
            "workspace_jail_enabled": True,
            "profile_name": "default",
            "langgraph_checkpoint_db_path": str(self.temp_dir / "checkpoints.db"),
        }
        if config_overrides:
            overrides.update(config_overrides)

        self.config: HolixRuntimeConfig = make_runtime_config(self.temp_dir, **overrides)
        self.llm = ScriptedLLM()
        self.agent: HolixAgent | None = None
        self._initialized = False
        self._confirm_choice: ConfirmationChoice | None = None
        self._confirm_handler: Any | None = None
        self.confirm_resolutions: list[tuple[str, str]] = []

        # In-memory checkpointer: no profile-bound SQLite dependency
        monkeypatch.setattr(
            "core.graph.builder.create_checkpointer",
            lambda **kwargs: create_checkpointer(use_persistent=False),
        )
        monkeypatch.setattr(
            "core.persistence.create_checkpointer",
            lambda **kwargs: create_checkpointer(use_persistent=False),
        )

    def auto_confirm(self, choice: ConfirmationChoice) -> UserCaseHarness:
        """Resolve every ConfirmationRequestEvent with *choice* (no TUI)."""
        self._confirm_choice = choice
        if self._initialized and self.agent is not None:
            self._install_confirm_resolver()
        return self

    def _install_confirm_resolver(self) -> None:
        assert self.agent is not None
        if self._confirm_handler is not None:
            self.agent.events.unsubscribe(self._confirm_handler)
            self._confirm_handler = None
        if self._confirm_choice is None:
            return

        choice = self._confirm_choice

        def _resolve(event: AgentEvent) -> None:
            if not isinstance(event, ConfirmationRequestEvent):
                return
            guard = getattr(getattr(self.agent, "tools", None), "_action_guard", None)
            if guard is None:
                return
            ok = guard.resolve_confirmation(event.confirmation_id, choice)
            if ok:
                self.confirm_resolutions.append((event.tool_name, choice.value))

        self._confirm_handler = _resolve
        self.agent.events.subscribe(_resolve)

    async def setup(self) -> UserCaseHarness:
        if self._initialized:
            return self
        self.agent = HolixAgent(config=self.config, enable_monitoring=False)
        await self.agent.initialize()
        self.llm.install(self.agent, self.monkeypatch)
        self._install_confirm_resolver()
        self._initialized = True
        return self

    def script(self, turns: list[Turn]) -> UserCaseHarness:
        self.llm.script(turns)
        return self

    async def run(
        self,
        user_input: str,
        *,
        conversation_id: str = "user_case",
        mode: str = "react",
        expect_exhausted: bool = True,
    ) -> JourneyResult:
        if not self._initialized or self.agent is None:
            await self.setup()
        assert self.agent is not None

        # Multi-turn safety
        self.agent._final_response_emitted = False
        if self.agent._execution_mode_last != mode:
            self.agent._graph = None
            self.agent._execution_mode_last = mode

        events: list[AgentEvent] = []

        def _capture(event: AgentEvent) -> None:
            events.append(event)

        self.agent.events.subscribe(_capture)
        try:
            return_value = await self.agent.run(
                user_input,
                conversation_id=conversation_id,
                execution_mode=mode,
            )
        finally:
            self.agent.events.unsubscribe(_capture)

        if expect_exhausted:
            self.llm.assert_exhausted()

        final_text = collect_final_text(events) or (return_value or "")
        return JourneyResult(
            events=events,
            final_text=final_text,
            return_value=return_value or "",
        )

    async def close(self) -> None:
        if self.agent is not None:
            if self._confirm_handler is not None:
                self.agent.events.unsubscribe(self._confirm_handler)
                self._confirm_handler = None
            await self.agent.close()
            self.agent = None
            self._initialized = False
