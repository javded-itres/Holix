import json
from typing import Any

from core.tools.aliases import apply_aliases_to_registry, infer_alias_action, resolve_tool_name
from core.tools.base import BaseTool, filter_execute_kwargs


class ToolRegistry:
    """Registry for managing and executing agent tools."""

    def __init__(
        self,
        *,
        workspace_root: str | None = None,
        workspace_jail_enabled: bool = False,
        profile_name: str = "default",
        tools_presentation: str = "native",
        tools_presentation_by_slot: dict[str, str] | None = None,
        code_mode_wall_timeout_s: int | None = None,
        code_mode_max_inner_calls: int | None = None,
        code_mode_parallel_readonly: bool | None = None,
    ):
        self.tools: dict[str, BaseTool] = {}
        self._action_guard = None  # Set by set_action_guard()
        self._workspace_root = workspace_root
        self._workspace_jail_enabled = workspace_jail_enabled
        self._profile_name = profile_name
        from core.tools.code_mode.policy import (
            DEFAULT_PARALLEL_READONLY,
            DEFAULT_WALL_S,
            MAX_INNER_CALLS,
            clamp_max_inner_calls,
            clamp_wall_timeout_s,
            normalize_presentation,
        )

        self._tools_presentation = normalize_presentation(tools_presentation)
        self._tools_presentation_by_slot = {
            str(k).strip().lower(): normalize_presentation(v)
            for k, v in (tools_presentation_by_slot or {}).items()
            if str(k).strip()
        }
        self._code_mode_wall_s = clamp_wall_timeout_s(code_mode_wall_timeout_s, DEFAULT_WALL_S)
        self._code_mode_max_inner = clamp_max_inner_calls(
            code_mode_max_inner_calls, MAX_INNER_CALLS
        )
        self._code_mode_parallel_readonly = (
            DEFAULT_PARALLEL_READONLY
            if code_mode_parallel_readonly is None
            else bool(code_mode_parallel_readonly)
        )

    def presentation_for_slot(self, slot: str = "main") -> str:
        from core.tools.code_mode.policy import normalize_presentation

        key = (slot or "main").strip().lower() or "main"
        if key in self._tools_presentation_by_slot:
            return self._tools_presentation_by_slot[key]
        return normalize_presentation(self._tools_presentation)

    def set_action_guard(self, guard) -> None:
        """Set the ActionGuard instance for pre-execution confirmation.

        When installed, all tool executions go through the guard's
        check_and_execute() method which classifies risk and may
        request confirmation before executing.

        Args:
            guard: An ActionGuard instance, or None to disable.
        """
        self._action_guard = guard

    def register(self, tool: BaseTool) -> None:
        """Register a tool in the registry.

        Args:
            tool: Tool instance to register.
        """
        self.tools[tool.name] = tool
        # Note: we no longer print here. The agent loop or higher level
        # can emit AgentEvent if it wants to surface tool registration.

    def unregister(self, name: str) -> bool:
        """Remove a tool by name. Returns True if it was present."""
        if name in self.tools:
            del self.tools[name]
            return True
        return False

    def register_alias(self, alias: str, tool: BaseTool) -> None:
        """Register an alternate name for an existing tool."""
        self.tools[alias] = tool

    def register_all(self) -> None:
        """Import and register all available tools."""
        from core.tools.apply_patch import ApplyPatchTool
        from core.tools.ask_user import AskUserTool
        from core.tools.code_executor import MathCalculatorTool, PythonExecutorTool
        from core.tools.database import SQLQueryTool, SQLSchemaTool
        from core.tools.file_ops import (
            DeleteFileTool,
            GlobTool,
            GrepTool,
            ListDirectoryTool,
            PatchFileTool,
            ReadFileTool,
            WriteFileTool,
        )
        from core.tools.job_monitor import JobMonitorTool
        from core.tools.lsp import LspTool
        from core.tools.notebook_edit import NotebookEditTool
        from core.tools.plan_mode import PlanModeTool
        from core.tools.send_chat_files import SendChatFilesTool
        from core.tools.session_memory import ReadSessionTool, SearchSessionsTool
        from core.tools.session_search import SessionSearchTool
        from core.tools.skills import SkillManageTool, SkillViewTool
        from core.tools.subagent_control import SubagentControlTool
        from core.tools.terminal import TerminalTool
        from core.tools.todo import TodoWriteTool
        from core.tools.tool_search import ToolSearchTool
        from core.tools.web_search import WebFetchTool, WebSearchTool

        # File operations
        self.register(ReadFileTool())
        self.register(WriteFileTool())
        self.register(PatchFileTool())
        self.register(ApplyPatchTool())
        self.register(NotebookEditTool())
        list_dir_tool = ListDirectoryTool()
        self.register(list_dir_tool)
        self.register_alias("list_dir", list_dir_tool)
        self.register(GrepTool())
        self.register(GlobTool())
        self.register(DeleteFileTool())

        from core.tools.holix_init import register_holix_init_tools

        register_holix_init_tools(self)

        # System
        terminal_tool = TerminalTool()
        self.register(terminal_tool)
        self.register_alias("terminal", terminal_tool)
        self.register_alias("execute_terminal_command", terminal_tool)
        from core.external_cli.platform import launch_supported

        if launch_supported():
            from core.tools.external_cli import ExternalCliTool

            self.register(ExternalCliTool())

        # Web
        self.register(WebSearchTool())
        fetch_tool = WebFetchTool()
        self.register(fetch_tool)
        self.register_alias("web_fetch", fetch_tool)

        # Database
        self.register(SQLQueryTool())
        self.register(SQLSchemaTool())

        # Code execution
        python_tool = PythonExecutorTool()
        self.register(python_tool)
        self.register_alias("code_executor", python_tool)
        calc_tool = MathCalculatorTool()
        self.register(calc_tool)
        self.register_alias("math_calculator", calc_tool)

        # Sub-agent ↔ user bridge
        self.register(AskUserTool())
        self.register(JobMonitorTool())
        self.register(SubagentControlTool())
        self.register(ToolSearchTool())
        self.register(SessionSearchTool())
        self.register(PlanModeTool())
        self.register(LspTool())

        # Session checklist (TUI / Telegram / MAX)
        self.register(TodoWriteTool())

        # Chat file delivery (Telegram; no-op without delivery bridge)
        self.register(SendChatFilesTool())

        # Cross-session memory
        self.register(SearchSessionsTool())
        self.register(ReadSessionTool())

        # Skills (progressive disclosure + staged writes)
        self.register(SkillViewTool())
        self.register(SkillManageTool())

        from core.tools.profile_identity import register_profile_identity_tools

        register_profile_identity_tools(self)

        from core.tools.background_process import register_background_process_tools

        register_background_process_tools(self)

        from core.tools.cron_schedule import register_cron_schedule_tool

        register_cron_schedule_tool(self)

        from core.tools.sdd import register_sdd_tools

        register_sdd_tools(self)

        from core.tools.acp import RunAcpAgentTool

        self.register(RunAcpAgentTool())

        from config import settings

        if settings.enable_browser_tools:
            from core.tools.browser import register_browser_tools

            register_browser_tools(self)

        try:
            from holix_studio.agent_tools.desktop import register_desktop_tools

            register_desktop_tools(self)
        except ImportError:
            pass

        from core.tools.code_mode.tool import RunCodeTool

        self.register(RunCodeTool(self))

        apply_aliases_to_registry(self)

    async def register_mcp(
        self,
        mcp_servers: dict[str, Any],
        assignments: dict[str, list[str]] | None = None,
        slot: str = "main",
        *,
        ready_timeout: float = 10.0,
    ) -> int:
        """Dynamically register MCP tools for this registry (called from agent init).

        ``slot`` is kept for callers; allow-lists are applied later in
        :meth:`get_schemas` / subagent runners so every assigned server
        is connected once.
        """
        del slot
        if not mcp_servers and not assignments:
            return 0
        try:
            from core.mcp.assign import fill_assigned_mcp_servers
            from core.mcp.manager import MCPManager

            servers = fill_assigned_mcp_servers(mcp_servers, assignments)
            if not servers:
                return 0
            mgr = MCPManager(servers)
            enabled = list(servers.keys())
            self._mcp_assignments = dict(assignments or {})  # type: ignore[attr-defined]
            self._mcp_enabled_servers = list(enabled)  # type: ignore[attr-defined]
            self._mcp_manager = mgr  # type: ignore[attr-defined]

            def _harvest(server_name: str | None = None) -> None:
                names = [server_name] if server_name else enabled
                for tool in mgr.get_tool_adapters(names):
                    if tool.name not in self.tools:
                        self.register(tool)

            mgr.on_tools_ready = _harvest
            await mgr.connect_all()
            # Register every connected server. Slot allow-lists are applied in
            # get_schemas / subagent runners so python-coder can use Context7
            # even when ``main`` only has holix_studio.
            # Give slow stdio servers (npx/uvx downloads, Context7 auth, etc.) time to initialize + list_tools
            try:
                await mgr.wait_ready(enabled or None, timeout=ready_timeout)
            except Exception:
                pass
            _harvest()
            return len([n for n in self.tools if str(n).startswith("mcp_")])
        except Exception as exc:
            # do not break agent if MCP misconfigured
            print(f"Warning: MCP registration skipped: {exc}")
            return 0

    async def finish_mcp_registration(self, *, timeout: float = 30.0) -> int:
        """Wait for slow MCP servers and register any tools not yet available."""
        mgr = getattr(self, "_mcp_manager", None)
        if not mgr:
            return 0
        enabled = getattr(self, "_mcp_enabled_servers", None) or list(mgr.available_servers)
        try:
            await mgr.wait_ready(enabled, timeout=timeout)
        except Exception:
            pass
        added = 0
        for tool in mgr.get_tool_adapters(enabled):
            if tool.name not in self.tools:
                self.register(tool)
                added += 1
        return added

    def mcp_status(self) -> list[dict[str, Any]]:
        """Ready/error snapshot for each MCP server this registry started."""
        mgr = getattr(self, "_mcp_manager", None)
        if mgr is None:
            return []
        status = getattr(mgr, "server_status", None)
        if callable(status):
            return list(status() or [])
        return []

    def get_end_tool_schemas(self, *, for_agent_slot: str = "main") -> list[dict[str, Any]]:
        """Schemas for real capabilities (never ``run_code``).

        Claude-style: only the core set plus ``tool_search`` hits enabled this
        session (``_session_enabled_tools``). Registered tools stay executable.
        """
        from core.mcp.assign import mcp_tool_allowed
        from core.tools.code_mode.policy import RUN_CODE_NAME
        from core.tools.lazy_schema import schema_tool_offered
        from core.tools.plan_mode_state import is_plan_mode
        from core.tools.slot_policy import (
            filter_schemas_for_plan_mode,
            tool_allowed_for_slot,
        )

        slot = (for_agent_slot or "main").strip().lower() or "main"
        assigns = getattr(self, "_mcp_assignments", None)
        session_extra = getattr(self, "_session_enabled_tools", None) or set()
        hidden_for_main = frozenset({"external_cli"})

        seen: set[str] = set()
        schemas: list[dict[str, Any]] = []
        for tool in self.tools.values():
            name = getattr(tool, "name", "") or ""
            if not name or name in seen:
                continue
            if name == RUN_CODE_NAME:
                continue
            if slot == "main" and name in hidden_for_main:
                continue
            if not tool_allowed_for_slot(name, slot):
                continue
            if not mcp_tool_allowed(name, slot=slot, assignments=assigns):
                continue
            if not schema_tool_offered(name, session_extra=session_extra):
                continue
            seen.add(name)
            schemas.append(tool.to_openai_schema())
        if is_plan_mode():
            schemas = filter_schemas_for_plan_mode(schemas)
        return schemas

    def get_schemas(self, *, for_agent_slot: str = "main") -> list[dict[str, Any]]:
        """Get OpenAI-compatible schemas for all registered tools.

        Returns:
            List of tool schemas
        """
        from core.tools.code_mode.policy import RUN_CODE_NAME

        end = self.get_end_tool_schemas(for_agent_slot=for_agent_slot)
        mode = self.presentation_for_slot(for_agent_slot)
        if mode == "native":
            return end
        run_tool = self.tools.get(RUN_CODE_NAME)
        if run_tool is None:
            return end
        run_schema = run_tool.to_openai_schema()
        if mode == "code":
            return [run_schema]
        return [*end, run_schema]

    async def execute(
        self,
        tool_call,
        conversation_id: str = "default",
        *,
        memory: Any = None,
        from_code_mode: bool = False,
    ) -> str:
        """Execute a tool call from the LLM.

        If an ActionGuard is installed, all tool executions go through
        check_and_execute() which classifies risk and may request
        user confirmation before executing.

        Args:
            tool_call: OpenAI tool call object
            conversation_id: Conversation ID for event correlation.

        Returns:
            str: Result of tool execution

        Raises:
            ValueError: If tool is not found
        """
        tool_name = tool_call.function.name
        resolved = resolve_tool_name(tool_name, self.tools)
        from core.tools.code_mode.policy import RUN_CODE_NAME
        from core.tools.execution_context import (
            from_code_mode_scope,
            get_agent_slot,
            reset_from_code_mode_scope,
            reset_tools_registry_scope,
            tools_registry_scope,
        )

        mode = self.presentation_for_slot(get_agent_slot())
        if mode == "code" and not from_code_mode and resolved != RUN_CODE_NAME:
            return (
                f"Error: only `{RUN_CODE_NAME}` is callable directly. "
                f"Wrap the call: `{RUN_CODE_NAME}(code="
                f'"return tools.{resolved}(...)" , description="…")`. '
                f"Do not call `{tool_name}` as a native function."
            )

        if resolved not in self.tools:
            return f"Error: Tool '{tool_name}' not found"

        try:
            from core.security.permission_preset import read_only_block_reason

            blocked = read_only_block_reason(
                resolved,
                profile=self._profile_name,
                conversation_id=conversation_id,
            )
            if blocked:
                return blocked
        except Exception:
            pass

        tool = self.tools[resolved]

        try:
            args = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError as e:
            return f"Error: Invalid JSON arguments - {e}"
        args = infer_alias_action(tool_name, resolved, args)

        try:
            from core.tools.plan_mode_state import is_plan_mode
            from core.tools.result import tool_err
            from core.tools.slot_policy import is_plan_mode_blocked

            if is_plan_mode() and is_plan_mode_blocked(resolved):
                return tool_err(
                    "plan_mode_blocked",
                    f"Tool '{resolved}' is blocked while plan_mode is on. "
                    "Call plan_mode(action='exit') after the plan is approved.",
                )
        except Exception:
            pass

        from core.crypto.unlock_context import (
            get_profile_session_dek,
            profile_unlock_scope,
            reset_profile_unlock_scope,
        )
        from core.tools.execution_context import (
            conversation_scope,
            get_tools_registry,
            memory_facade_scope,
            profile_scope,
            reset_conversation_scope,
            reset_memory_facade_scope,
            reset_profile_scope,
            reset_workspace_scope,
            workspace_scope,
        )
        from core.workspace import sanitize_paths_in_text

        token = conversation_scope(conversation_id)
        mem_token = memory_facade_scope(memory) if memory is not None else None
        profile_token = profile_scope(self._profile_name)
        existing_reg = get_tools_registry()
        reg_token = tools_registry_scope(self) if existing_reg is None else None
        code_mode_token = from_code_mode_scope(from_code_mode=from_code_mode)
        ws_tokens = workspace_scope(
            workspace_root=self._workspace_root,
            workspace_jail_enabled=self._workspace_jail_enabled,
        )
        dek = get_profile_session_dek(self._profile_name)
        unlock_tokens = (
            profile_unlock_scope(profile=self._profile_name, dek=dek) if dek is not None else []
        )
        try:
            from core.tools.execution_context import is_run_cancelled

            if is_run_cancelled():
                return sanitize_paths_in_text(
                    f"Error: Run cancelled — tool '{tool_name}' not executed."
                )
            # Gate with ActionGuard if installed
            try:
                if self._action_guard:
                    result = await self._action_guard.check_and_execute(
                        tool_name=tool_name,
                        tool_instance=tool,
                        arguments=args,
                        execute_fn=tool.execute,
                        conversation_id=conversation_id,
                    )
                    return sanitize_paths_in_text(result) if isinstance(result, str) else result

                # No guard: execute directly (backward compatible)
                result = await tool.execute(**filter_execute_kwargs(tool.execute, args))
                return sanitize_paths_in_text(result) if isinstance(result, str) else result
            except Exception as e:
                return sanitize_paths_in_text(f"Error executing {tool_name}: {str(e)}")
        finally:
            reset_conversation_scope(token)
            if mem_token is not None:
                reset_memory_facade_scope(mem_token)
            reset_profile_scope(profile_token)
            if reg_token is not None:
                reset_tools_registry_scope(reg_token)
            reset_from_code_mode_scope(code_mode_token)
            reset_workspace_scope(ws_tokens)
            if unlock_tokens:
                reset_profile_unlock_scope(unlock_tokens)

    def get_tool_names(self) -> list[str]:
        """Get names of all registered tools.

        Returns:
            List of tool names
        """
        return list(self.tools.keys())
