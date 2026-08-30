"""Live LLM harness: real provider, isolated temp workspace, auto cleanup."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

from core.agent import HolixAgent
from core.agent_events import AgentEvent
from core.di.runtime_config import HolixRuntimeConfig
from core.security.confirmation import ConfirmationChoice
from core.security.confirmation_events import ConfirmationRequestEvent

from tests.live_llm.provider import LiveProvider, extract_final

_RETRY_MARKERS = (
    "без видимого ответа",
    "without a visible answer",
    "finished reasoning without",
    "request timed out",
    "connection error",
    "error during agent step",
    "попробуйте ещё раз",
)


class LiveResult:
    def __init__(
        self,
        *,
        events: list[AgentEvent],
        final_text: str,
        return_value: str,
        workspace: Path,
        artifacts_dir: Path,
    ) -> None:
        self.events = events
        self.final_text = final_text
        self.return_value = return_value
        self.workspace = workspace
        self.artifacts_dir = artifacts_dir

    @property
    def text(self) -> str:
        return self.final_text or self.return_value or ""

    def tool_names(self) -> list[str]:
        from core.agent_events import ToolCallStartEvent

        return [e.tool_name for e in self.events if isinstance(e, ToolCallStartEvent)]

    def called(self, name: str) -> bool:
        return name in self.tool_names()

    def tool_payloads(self, name: str) -> list[Any]:
        """JSON bodies from tool results for ``name`` (best-effort)."""
        import json

        out: list[Any] = []
        for event in self.events:
            if getattr(event, "tool_name", None) != name:
                continue
            raw = getattr(event, "result", None)
            if raw is None:
                err = getattr(event, "error", None)
                if err:
                    out.append({"ok": False, "error": str(err)})
                continue
            text = str(raw).strip()
            if text.startswith("{") or text.startswith("["):
                try:
                    out.append(json.loads(text))
                    continue
                except json.JSONDecodeError:
                    pass
            out.append({"raw": text})
        return out

    def confirmation_tools(self) -> list[str]:
        return [e.tool_name for e in self.events if isinstance(e, ConfirmationRequestEvent)]

    def looks_unreliable(self) -> bool:
        low = self.text.lower()
        if not low.strip():
            return True
        return any(m in low for m in _RETRY_MARKERS)


class LiveHarness:
    """Real HolixAgent against a live provider; all side effects under temp dirs."""

    def __init__(
        self,
        root: Path,
        provider: LiveProvider,
        monkeypatch: Any,
        *,
        auto_allow_threshold: str = "high",
        enable_browser: bool = False,
        max_steps: int = 18,
        confirm_choice: ConfirmationChoice | None = None,
        browser_allowed_hosts: str = "example.com,en.wikipedia.org,wikipedia.org",
    ) -> None:
        self.root = Path(root)
        self.provider = provider
        self.monkeypatch = monkeypatch
        self.workspace = self.root / "workspace"
        self.artifacts_dir = self.root / "artifacts"
        self.data_dir = self.root / "data"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "security").mkdir(parents=True, exist_ok=True)

        monkeypatch.setenv("HOLIX_AGENT_EXTENSIONS_OFF", "1")
        monkeypatch.setenv("HOLIX_UNATTENDED", "0")

        self.config = HolixRuntimeConfig.from_settings().with_overrides(
            model=provider.model,
            base_url=provider.base_url,
            api_key=provider.api_key,
            data_dir=str(self.data_dir),
            memory_db_path=str(self.root / "mem.db"),
            vector_db_path=str(self.root / "vec"),
            ltm_db_path=str(self.root / "ltm.db"),
            skills_dir=str(self.root / "skills"),
            langgraph_checkpoint_db_path=str(self.root / "checkpoints.db"),
            enable_long_term_memory=False,
            use_langgraph=True,
            execution_mode="react",
            auto_allow_threshold=auto_allow_threshold,
            non_interactive=False,
            confirmation_timeout=15,
            plan_review_enabled=False,
            enable_meta_agent=False,
            enable_self_refinement=False,
            enable_subagents=False,
            enable_browser_tools=enable_browser,
            browser_headless=True,
            browser_allowed_hosts=browser_allowed_hosts,
            mcp_enabled=False,
            self_extensions_enabled=False,
            max_steps=max_steps,
            max_steps_extend_enabled=False,
            llm_step_timeout=600.0,
            workspace_root=str(self.workspace),
            workspace_jail_enabled=True,
            profile_name="default",
            temperature=0.1,
            search={
                "strategy": "first_success",
                "providers": ["duckduckgo"],
                "duckduckgo": {"enabled": True},
            },
        )
        self.agent: HolixAgent | None = None
        self._confirm_choice = confirm_choice
        self._confirm_handler: Any | None = None
        self._closed = False

    async def setup(self) -> LiveHarness:
        self.agent = HolixAgent(config=self.config, enable_monitoring=False)
        await self.agent.initialize()

        # Force ReAct to use agent.client (config model/base_url/api_key).
        class _NoModelManager:
            def __bool__(self) -> bool:
                return False

        self.agent._model_manager = _NoModelManager()
        try:
            from core.models.client_factory import create_openai_client
            from core.search.engine import set_search_config

            self.agent.client = create_openai_client(
                base_url=self.provider.base_url,
                api_key=self.provider.api_key,
            )
            self.agent.model = self.provider.model
            # Ensure web_search uses DDG even under isolated profile
            set_search_config(self.config.search)
            if hasattr(self.agent, "search") and self.agent.search is not None:
                try:
                    from core.search.config import SearchConfig
                    from core.search.engine import SearchEngine

                    self.agent.search = SearchEngine(SearchConfig.from_dict(self.config.search))
                except Exception:
                    pass
        except Exception:
            pass
        if self._confirm_choice is not None:
            self._install_confirm_resolver()
        return self

    def stub_ask_user(self, answer: str = "dark") -> None:
        """Replace the TUI/Telegram ask_user wait with an immediate answer."""
        assert self.agent is not None

        class _StubBridge:
            async def ask_user(self, name, question, *, context="", questions=None):
                import json as _json

                qid = "q1"
                if isinstance(questions, list) and questions:
                    qid = str(questions[0].get("id") or "q1")
                return _json.dumps({qid: [answer]})

        self.agent.subagents.interactions = _StubBridge()

    def _install_confirm_resolver(self) -> None:
        assert self.agent is not None
        choice = self._confirm_choice

        def _resolve(event: AgentEvent) -> None:
            if not isinstance(event, ConfirmationRequestEvent):
                return
            guard = getattr(getattr(self.agent, "tools", None), "_action_guard", None)
            if guard is None:
                return
            guard.resolve_confirmation(event.confirmation_id, choice)

        self._confirm_handler = _resolve
        self.agent.events.subscribe(_resolve)

    async def _run_once(
        self,
        user_input: str,
        *,
        conversation_id: str,
        mode: str,
        timeout_s: float,
    ) -> LiveResult:
        assert self.agent is not None
        self.agent._final_response_emitted = False
        if self.agent._execution_mode_last != mode:
            self.agent._graph = None
            self.agent._execution_mode_last = mode

        events: list[AgentEvent] = []

        def _capture(event: AgentEvent) -> None:
            events.append(event)

        self.agent.events.subscribe(_capture)
        try:
            return_value = await asyncio.wait_for(
                self.agent.run(
                    user_input,
                    conversation_id=conversation_id,
                    execution_mode=mode,
                ),
                timeout=timeout_s,
            )
        except TimeoutError:
            return LiveResult(
                events=events,
                final_text="Error during agent step: Request timed out.",
                return_value="Error during agent step: Request timed out.",
                workspace=self.workspace,
                artifacts_dir=self.artifacts_dir,
            )
        finally:
            self.agent.events.unsubscribe(_capture)

        final_text = extract_final(events, return_value or "")
        return LiveResult(
            events=events,
            final_text=final_text,
            return_value=return_value or "",
            workspace=self.workspace,
            artifacts_dir=self.artifacts_dir,
        )

    async def run(
        self,
        user_input: str,
        *,
        conversation_id: str = "live",
        mode: str = "react",
        timeout_s: float = 480.0,
        retries: int = 2,
    ) -> LiveResult:
        if self.agent is None:
            await self.setup()
        assert self.agent is not None

        result = await self._run_once(
            user_input,
            conversation_id=conversation_id,
            mode=mode,
            timeout_s=timeout_s,
        )
        attempt = 0
        while result.looks_unreliable() and attempt < retries:
            attempt += 1
            nudge = (
                f"{user_input}\n\n"
                "IMPORTANT: Put the final answer in the assistant message content "
                "(visible reply), not only in internal reasoning. "
                "If tools are useful, call them. Keep the final answer short and explicit."
            )
            result = await self._run_once(
                nudge,
                conversation_id=f"{conversation_id}_retry{attempt}",
                mode=mode,
                timeout_s=timeout_s,
            )
        return result

    def seed(self, relative: str, content: str) -> Path:
        path = self.workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def read(self, relative: str) -> str:
        return (self.workspace / relative).read_text(encoding="utf-8")

    def exists(self, relative: str) -> bool:
        return (self.workspace / relative).exists()

    def list_workspace(self) -> list[str]:
        if not self.workspace.exists():
            return []
        return sorted(
            str(p.relative_to(self.workspace)) for p in self.workspace.rglob("*") if p.is_file()
        )

    def snapshot_artifacts(self, label: str) -> Path:
        """Copy workspace into artifacts/<label> for post-mortem before cleanup."""
        dest = self.artifacts_dir / label
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        if self.workspace.exists():
            shutil.copytree(self.workspace, dest, dirs_exist_ok=True)
        return dest

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.agent is not None:
            if self._confirm_handler is not None:
                self.agent.events.unsubscribe(self._confirm_handler)
            try:
                # Close browser sessions if any
                try:
                    from core.tools.browser.session import get_browser_session_manager

                    await get_browser_session_manager().close_all()
                except Exception:
                    pass
                await self.agent.close()
            except Exception:
                pass
            self.agent = None
        shutil.rmtree(self.root, ignore_errors=True)
