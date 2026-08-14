"""Testable Holix TUI app with mock agent + pilot helpers."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from cli.core import ProfileConfig, ProfileManager, init_profile
from cli.tui.code.app import HolixCodeApp
from cli.tui.code.widgets import CodePrompt
from core.agent_events import AgentEventBus


def make_mock_agent(*, reply: str = "mock-assistant-reply") -> MagicMock:
    """Agent double used by TUI pilot tests (no real LLM)."""
    agent = MagicMock()
    agent.run = AsyncMock(return_value=reply)
    agent.close = AsyncMock()
    bus = AgentEventBus(name="tui-test")
    agent.events = bus
    agent.emit = bus.emit
    agent.tools = MagicMock()
    agent.tools._action_guard = None
    # Critical: MagicMock auto-creates .subagents → try_route_subagent_reply
    # would hijack every plain message. Keep subagents absent.
    agent.subagents = None
    agent.memory = MagicMock()
    agent.memory.get_conversation = AsyncMock(return_value=[])
    agent.memory.save_message = AsyncMock()
    agent.config = MagicMock()
    agent.config.auto_allow_threshold = "low"
    agent.config.non_interactive = False
    agent.config.execution_mode = "react"
    agent._initialized = True
    agent._event_context = None
    return agent


class TestableHolixCodeApp(HolixCodeApp):
    """HolixCodeApp that injects a mock agent instead of create_agent."""

    def __init__(
        self,
        profile: str = "default",
        config: ProfileConfig | None = None,
        *,
        mock_agent: Any | None = None,
        use_real_agent: bool = False,
    ):
        super().__init__(profile=profile, config=config)
        self._mock_agent = mock_agent
        self._use_real_agent = use_real_agent
        self._init_done = asyncio.Event()

    async def _initialize_agent(self) -> None:
        if self._use_real_agent:
            await super()._initialize_agent()
            self._init_done.set()
            return

        self._agent_init_state = "initializing"
        agent = self._mock_agent or make_mock_agent()
        # Wire event bus like production
        if hasattr(agent, "events") and agent.events is not None:
            try:
                agent.events.subscribe(self._on_agent_event)
            except Exception:
                pass
        self.agent = agent
        self._resolved_model = "mock-model"
        self.transcript_write("[dim]ready — type a message or /help[/dim]\n")
        self.set_status_line("ready")
        self._agent_init_state = "ready"
        self._set_prompt_enabled(True)
        self._init_done.set()

    async def wait_ready(self, timeout: float = 15.0) -> None:
        await asyncio.wait_for(self._init_done.wait(), timeout=timeout)
        # Prompt enable is UI-thread; give compose a beat
        await asyncio.sleep(0.15)
        # Deterministic mode for tests (ignore persisted UI state)
        self._execution_mode_index = 0

    def transcript_plain(self) -> str:
        """Join displayed transcript chunks (Rich markup included as str)."""
        parts: list[str] = []
        for chunk in self._transcript_display_chunks:
            parts.append(str(chunk))
        # Prefer store when populated
        try:
            stored = self._transcript_store.format_all()
            if stored.strip():
                parts.append(stored)
        except Exception:
            pass
        return "\n".join(parts)

    def status_text(self) -> str:
        try:
            bar = self.query_one("#status-bar")
            return str(getattr(bar, "renderable", "") or bar)
        except Exception:
            return ""

    async def type_and_submit(self, pilot: Any, text: str) -> None:
        """Focus prompt, load text, press Enter (send)."""
        prompt = self.query_one("#input-area", CodePrompt)
        await pilot.click("#input-area")
        await pilot.pause(0.15)
        prompt.load_text(text)
        await pilot.pause(0.15)
        await pilot.press("enter")
        await pilot.pause(0.35)


@asynccontextmanager
async def launch_tui(
    *,
    profile: str = "default",
    mock_agent: Any | None = None,
    use_real_agent: bool = False,
    size: tuple[int, int] = (120, 40),
) -> AsyncIterator[tuple[TestableHolixCodeApp, Any]]:
    """Launch full Holix TUI under Textual pilot; yields (app, pilot)."""
    # Ensure profile exists under isolated HOLIX_HOME (conftest fixture)
    pm = ProfileManager()
    if not pm.profile_exists(profile):
        pm.create_profile(profile)
    cfg = init_profile(profile)

    app = TestableHolixCodeApp(
        profile=profile,
        config=cfg,
        mock_agent=mock_agent,
        use_real_agent=use_real_agent,
    )
    async with app.run_test(size=size) as pilot:
        await app.wait_ready()
        yield app, pilot
