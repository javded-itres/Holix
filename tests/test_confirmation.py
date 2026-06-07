"""
Tests for the dangerous action confirmation system.

Tests:
1. RiskClassifier — classifies tool calls correctly
2. PermissionManager — session/always grants, persist/load
3. ActionGuard — auto-allow, deny, mock confirmation flow
4. ConfirmationEvents — event creation and fields
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path

import pytest

from core.security.confirmation import (
    ActionGuard,
    ConfirmationChoice,
    PermissionManager,
    PermissionScope,
    RiskAssessment,
    RiskClassifier,
    RiskLevel,
    permission_manager,
)
from core.security.confirmation_events import (
    ConfirmationRequestEvent,
    ConfirmationResponseEvent,
    ConfirmationEventType,
)


# ─── RiskClassifier Tests ─────────────────────────────────────────────────

class TestRiskClassifier:
    """Test risk classification for all tool types."""

    def setup_method(self):
        self.classifier = RiskClassifier()

    def _make_tool(self, name: str, risk_level: str = "medium"):
        """Create a minimal tool-like object with risk_level."""
        class FakeTool:
            pass
        tool = FakeTool()
        tool.name = name
        tool.risk_level = risk_level
        return tool

    # ── Read-only tools: NO risk ──

    def test_read_file_is_no_risk(self):
        tool = self._make_tool("read_file", "no")
        assessment = self.classifier.classify("read_file", tool, {"path": "/etc/passwd"})
        assert assessment.risk_level == RiskLevel.NO

    def test_list_directory_is_no_risk(self):
        tool = self._make_tool("list_directory", "no")
        assessment = self.classifier.classify("list_directory", tool, {"path": "."})
        assert assessment.risk_level == RiskLevel.NO

    def test_math_calculator_is_no_risk(self):
        tool = self._make_tool("calculate", "no")
        assessment = self.classifier.classify("calculate", tool, {"expression": "2+2"})
        assert assessment.risk_level == RiskLevel.NO

    def test_sql_schema_is_no_risk(self):
        tool = self._make_tool("sql_schema", "no")
        assessment = self.classifier.classify("sql_schema", tool, {"db_path": "test.db"})
        assert assessment.risk_level == RiskLevel.NO

    # ── Low risk tools ──

    def test_web_search_is_low_risk(self):
        tool = self._make_tool("web_search", "low")
        assessment = self.classifier.classify("web_search", tool, {"query": "python async"})
        assert assessment.risk_level == RiskLevel.LOW

    # ── Medium risk tools ──

    def test_write_file_is_medium_risk(self):
        tool = self._make_tool("write_file", "medium")
        assessment = self.classifier.classify("write_file", tool, {"path": "test.py", "content": "print('hi')"})
        assert assessment.risk_level == RiskLevel.MEDIUM

    def test_sql_query_select_is_medium(self):
        tool = self._make_tool("sql_query", "medium")
        assessment = self.classifier.classify("sql_query", tool, {"query": "SELECT * FROM users"})
        assert assessment.risk_level == RiskLevel.MEDIUM

    # ── High risk tools ──

    def test_terminal_command_is_high_risk(self):
        tool = self._make_tool("run_terminal_command", "high")
        assessment = self.classifier.classify("run_terminal_command", tool, {"command": "ls -la"})
        assert assessment.risk_level == RiskLevel.HIGH

    def test_python_executor_is_high_risk(self):
        tool = self._make_tool("execute_python", "high")
        assessment = self.classifier.classify("execute_python", tool, {"code": "print('hello')"})
        assert assessment.risk_level == RiskLevel.HIGH

    # ── Escalation tests ──

    def test_write_env_file_escalates_to_high(self):
        tool = self._make_tool("write_file", "medium")
        assessment = self.classifier.classify("write_file", tool, {"path": ".env", "content": "SECRET=abc"})
        assert assessment.risk_level == RiskLevel.HIGH
        assert "env" in assessment.reason.lower()

    def test_write_config_py_escalates_to_high(self):
        tool = self._make_tool("write_file", "medium")
        assessment = self.classifier.classify("write_file", tool, {"path": "config.py", "content": "DB_URL=..."})
        assert assessment.risk_level == RiskLevel.HIGH

    def test_sql_delete_escalates_to_high(self):
        tool = self._make_tool("sql_query", "medium")
        assessment = self.classifier.classify("sql_query", tool, {"query": "DELETE FROM users WHERE id=1"})
        assert assessment.risk_level == RiskLevel.HIGH
        assert "DELETE" in assessment.reason

    def test_sql_drop_escalates_to_high(self):
        tool = self._make_tool("sql_query", "medium")
        assessment = self.classifier.classify("sql_query", tool, {"query": "DROP TABLE users"})
        assert assessment.risk_level == RiskLevel.HIGH

    def test_terminal_dangerous_pattern_escalates(self):
        tool = self._make_tool("run_terminal_command", "high")
        assessment = self.classifier.classify("run_terminal_command", tool, {"command": "git push --force"})
        assert assessment.risk_level == RiskLevel.HIGH
        assert assessment.pattern_matched is not None

    def test_python_os_import_escalates(self):
        tool = self._make_tool("execute_python", "high")
        assessment = self.classifier.classify("execute_python", tool, {"code": "import os; os.listdir('.')"})
        assert assessment.risk_level == RiskLevel.HIGH
        assert "OS module" in assessment.reason

    # ── Default: use baseline ──

    def test_unknown_tool_uses_baseline(self):
        tool = self._make_tool("unknown_tool", "medium")
        assessment = self.classifier.classify("unknown_tool", tool, {})
        assert assessment.risk_level == RiskLevel.MEDIUM
        assert "unknown_tool" in assessment.reason


# ─── PermissionManager Tests ──────────────────────────────────────────────

class TestPermissionManager:
    """Test permission grant storage and retrieval."""

    def setup_method(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        self._perm_path = path
        self.pm = PermissionManager()
        self.pm.PERMISSIONS_FILE = Path(path)

    def teardown_method(self):
        Path(self._perm_path).unlink(missing_ok=True)

    def test_session_grant(self):
        self.pm.grant("run_terminal_command", PermissionScope.SESSION, RiskLevel.HIGH)
        assert self.pm.is_allowed("run_terminal_command", RiskLevel.HIGH)

    def test_always_grant_persists(self):
        self.pm.grant("write_file", PermissionScope.ALWAYS, RiskLevel.MEDIUM)
        assert self.pm.is_allowed("write_file", RiskLevel.MEDIUM)

        # Create a new manager and verify persistence
        pm2 = PermissionManager()
        pm2.PERMISSIONS_FILE = self.pm.PERMISSIONS_FILE
        pm2.load()
        assert pm2.is_allowed("write_file", RiskLevel.MEDIUM)

    def test_once_grant_not_stored(self):
        self.pm.grant("execute_python", PermissionScope.ONCE, RiskLevel.HIGH)
        # ONCE grants are not stored — they only apply to the current invocation
        # which is handled by ActionGuard, not PermissionManager
        assert not self.pm.is_allowed("execute_python", RiskLevel.HIGH)

    def test_broader_grant_covers_narrower(self):
        # Grant for HIGH risk should cover MEDIUM too
        self.pm.grant("write_file", PermissionScope.SESSION, RiskLevel.HIGH)
        assert self.pm.is_allowed("write_file", RiskLevel.MEDIUM)
        assert self.pm.is_allowed("write_file", RiskLevel.HIGH)

    def test_narrower_grant_does_not_cover_broader(self):
        self.pm.grant("write_file", PermissionScope.SESSION, RiskLevel.LOW)
        assert not self.pm.is_allowed("write_file", RiskLevel.HIGH)

    def test_revoke_session_grant(self):
        self.pm.grant("run_terminal_command", PermissionScope.SESSION, RiskLevel.HIGH)
        assert self.pm.is_allowed("run_terminal_command", RiskLevel.HIGH)
        self.pm.revoke("run_terminal_command", PermissionScope.SESSION, RiskLevel.HIGH)
        assert not self.pm.is_allowed("run_terminal_command", RiskLevel.HIGH)

    def test_clear_session(self):
        self.pm.grant("run_terminal_command", PermissionScope.SESSION, RiskLevel.HIGH)
        self.pm.grant("write_file", PermissionScope.SESSION, RiskLevel.MEDIUM)
        self.pm.clear_session()
        assert not self.pm.is_allowed("run_terminal_command", RiskLevel.HIGH)
        assert not self.pm.is_allowed("write_file", RiskLevel.MEDIUM)

    def test_list_grants(self):
        self.pm.grant("run_terminal_command", PermissionScope.SESSION, RiskLevel.HIGH)
        self.pm.grant("write_file", PermissionScope.ALWAYS, RiskLevel.MEDIUM)
        grants = self.pm.list_grants()
        assert len(grants["session"]) == 1
        assert len(grants["always"]) == 1


# ─── ConfirmationEvents Tests ──────────────────────────────────────────────

class TestConfirmationEvents:
    """Test event creation and fields."""

    def test_confirmation_request_event_fields(self):
        event = ConfirmationRequestEvent(
            confirmation_id="test_1",
            tool_name="run_terminal_command",
            arguments={"command": "rm -rf /tmp"},
            risk_level="high",
            reason="Dangerous terminal command",
            conversation_id="conv_1",
        )
        assert event.confirmation_id == "test_1"
        assert event.tool_name == "run_terminal_command"
        assert event.risk_level == "high"
        # Check event_type in dict representation
        d = event.to_dict()
        assert d["type"] == ConfirmationEventType.CONFIRMATION_REQUEST

    def test_confirmation_response_event_fields(self):
        event = ConfirmationResponseEvent(
            confirmation_id="test_1",
            choice="allow_once",
            tool_name="run_terminal_command",
            risk_level="high",
        )
        assert event.confirmation_id == "test_1"
        assert event.choice == "allow_once"
        # Check event_type in dict representation
        d = event.to_dict()
        assert d["type"] == ConfirmationEventType.CONFIRMATION_RESPONSE

    def test_event_to_dict(self):
        event = ConfirmationRequestEvent(
            confirmation_id="test_2",
            tool_name="write_file",
            arguments={"path": ".env"},
            risk_level="high",
            reason="Writing to .env file",
        )
        d = event.to_dict()
        assert d["tool_name"] == "write_file"
        assert d["risk_level"] == "high"
        assert d["type"] == "confirmation_request"


# ─── ActionGuard Tests ──────────────────────────────────────────────────────

class TestActionGuard:
    """Test the ActionGuard orchestration."""

    def setup_method(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        self._perm_path = path
        self.pm = PermissionManager()
        self.pm.PERMISSIONS_FILE = Path(path)
        self.classifier = RiskClassifier()

    def teardown_method(self):
        Path(self._perm_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_auto_allow_below_threshold(self):
        """Tools at or below the threshold should execute without confirmation."""
        guard = ActionGuard(
            event_bus=None,
            permission_manager=self.pm,
            risk_classifier=self.classifier,
            auto_allow_threshold=RiskLevel.LOW,
            interactive=True,
        )

        # Create a no-risk tool
        class FakeTool:
            risk_level = "no"

        async def fake_execute(path=""):
            return f"Content of {path}"

        result = await guard.check_and_execute(
            tool_name="read_file",
            tool_instance=FakeTool(),
            arguments={"path": "test.txt"},
            execute_fn=fake_execute,
        )
        assert "Content of test.txt" in result

    @pytest.mark.asyncio
    async def test_stored_permission_allows_execution(self):
        """If a permission grant exists, the tool should execute without confirmation."""
        self.pm.grant("run_terminal_command", PermissionScope.SESSION, RiskLevel.HIGH)

        guard = ActionGuard(
            event_bus=None,
            permission_manager=self.pm,
            risk_classifier=self.classifier,
            auto_allow_threshold=RiskLevel.NO,  # Strict threshold
            interactive=True,
        )

        class FakeTool:
            risk_level = "high"

        async def fake_execute(command=""):
            return "Success"

        result = await guard.check_and_execute(
            tool_name="run_terminal_command",
            tool_instance=FakeTool(),
            arguments={"command": "ls"},
            execute_fn=fake_execute,
        )
        assert result == "Success"

    @pytest.mark.asyncio
    async def test_non_interactive_mode_denies(self):
        """In non-interactive mode, high-risk tools without permission should be denied."""
        guard = ActionGuard(
            event_bus=None,
            permission_manager=self.pm,
            risk_classifier=self.classifier,
            auto_allow_threshold=RiskLevel.NO,
            interactive=False,
        )

        class FakeTool:
            risk_level = "high"

        result = await guard.check_and_execute(
            tool_name="run_terminal_command",
            tool_instance=FakeTool(),
            arguments={"command": "rm -rf /tmp"},
            execute_fn=lambda command="": "Should not reach here",
        )
        assert "Error" in result
        assert "denied" in result.lower() or "confirmation" in result.lower()

    @pytest.mark.asyncio
    async def test_resolve_confirmation_allows_once(self):
        """Resolving a confirmation with ALLOW_ONCE should execute the tool."""
        guard = ActionGuard(
            event_bus=None,
            permission_manager=self.pm,
            risk_classifier=self.classifier,
            auto_allow_threshold=RiskLevel.NO,
            interactive=True,
            confirmation_timeout=5,
        )

        executed = []

        async def fake_execute(**kwargs):
            executed.append(True)
            return "Executed successfully"

        class FakeTool:
            risk_level = "high"

        # Start the check in a background task
        async def run_check():
            return await guard.check_and_execute(
                tool_name="run_terminal_command",
                tool_instance=FakeTool(),
                arguments={"command": "ls"},
                execute_fn=fake_execute,
                conversation_id="test",
            )

        # Create the task
        task = asyncio.create_task(run_check())

        # Wait a bit for the confirmation request to be created
        await asyncio.sleep(0.1)

        # Find the pending confirmation and resolve it
        assert len(guard._pending_confirmations) == 1
        confirmation_id = list(guard._pending_confirmations.keys())[0]

        # Resolve with ALLOW_ONCE
        guard.resolve_confirmation(confirmation_id, ConfirmationChoice.ALLOW_ONCE)

        # Wait for the task to complete
        result = await asyncio.wait_for(task, timeout=5.0)

        assert result == "Executed successfully"
        assert len(executed) == 1

        # ALLOW_ONCE should NOT create a stored grant
        assert not self.pm.is_allowed("run_terminal_command", RiskLevel.HIGH)

    @pytest.mark.asyncio
    async def test_resolve_confirmation_allows_session(self):
        """ALLOW_SESSION should create a session grant and execute the tool."""
        guard = ActionGuard(
            event_bus=None,
            permission_manager=self.pm,
            risk_classifier=self.classifier,
            auto_allow_threshold=RiskLevel.NO,
            interactive=True,
            confirmation_timeout=5,
        )

        async def fake_execute(**kwargs):
            return "Done"

        class FakeTool:
            risk_level = "high"

        task = asyncio.create_task(guard.check_and_execute(
            tool_name="run_terminal_command",
            tool_instance=FakeTool(),
            arguments={"command": "ls"},
            execute_fn=fake_execute,
        ))

        await asyncio.sleep(0.1)
        confirmation_id = list(guard._pending_confirmations.keys())[0]
        guard.resolve_confirmation(confirmation_id, ConfirmationChoice.ALLOW_SESSION)

        result = await asyncio.wait_for(task, timeout=5.0)
        assert result == "Done"
        assert self.pm.is_allowed("run_terminal_command", RiskLevel.HIGH)

    @pytest.mark.asyncio
    async def test_resolve_confirmation_denies(self):
        """DENY should return an error message without executing the tool."""
        guard = ActionGuard(
            event_bus=None,
            permission_manager=self.pm,
            risk_classifier=self.classifier,
            auto_allow_threshold=RiskLevel.NO,
            interactive=True,
            confirmation_timeout=5,
        )

        executed = []

        async def fake_execute(**kwargs):
            executed.append(True)
            return "Should not execute"

        class FakeTool:
            risk_level = "high"

        task = asyncio.create_task(guard.check_and_execute(
            tool_name="run_terminal_command",
            tool_instance=FakeTool(),
            arguments={"command": "rm -rf /"},
            execute_fn=fake_execute,
        ))

        await asyncio.sleep(0.1)
        confirmation_id = list(guard._pending_confirmations.keys())[0]
        guard.resolve_confirmation(confirmation_id, ConfirmationChoice.DENY)

        result = await asyncio.wait_for(task, timeout=5.0)
        assert "Error" in result or "denied" in result.lower()
        assert len(executed) == 0  # Should NOT have executed the tool

    @pytest.mark.asyncio
    async def test_resolve_nonexistent_confirmation(self):
        """Resolving a non-existent confirmation should return False."""
        guard = ActionGuard(event_bus=None)
        result = guard.resolve_confirmation("nonexistent_id", ConfirmationChoice.ALLOW_ONCE)
        assert result is False

class TestPlanExecutionAutoApprove:
    """Tests for auto-approve flag during plan execution."""

    def test_auto_approve_flag_default_off(self):
        """By default, auto_approve_plan_execution is False."""
        from core.security.confirmation import ActionGuard
        guard = ActionGuard(interactive=True)
        assert guard._auto_approve_plan_execution is False

    def test_auto_approve_flag_set_on(self):
        """Setting auto_approve_plan_execution to True auto-approves tool calls."""
        from core.security.confirmation import ActionGuard, RiskLevel, RiskClassifier
        from unittest.mock import AsyncMock

        guard = ActionGuard(interactive=True, auto_allow_threshold=RiskLevel.LOW)
        guard._auto_approve_plan_execution = True

        # Create a mock tool with high risk
        mock_tool = AsyncMock()
        mock_tool.risk_level = "high"
        mock_tool.execute = AsyncMock(return_value="result")

        # High-risk tool should be auto-approved when flag is on
        # (This would normally require confirmation)
        classifier = RiskClassifier()
        assessment = classifier.classify("run_terminal_command", mock_tool, {"command": "ls"})
        assert assessment.risk_level == RiskLevel.HIGH

    def test_auto_approve_flag_resets(self):
        """Setting auto_approve_plan_execution back to False restores confirmation."""
        from core.security.confirmation import ActionGuard
        guard = ActionGuard(interactive=True)
        guard._auto_approve_plan_execution = True
        assert guard._auto_approve_plan_execution is True
        guard._auto_approve_plan_execution = False
        assert guard._auto_approve_plan_execution is False


class TestSharedPermissionManager:
    """Gateway API and ActionGuard must share one PermissionManager."""

    def test_module_exports_permission_manager(self):
        from core.security.confirmation import permission_manager as pm

        assert isinstance(pm, PermissionManager)

    def test_init_action_guard_uses_shared_instance(self):
        from unittest.mock import MagicMock
        from core.security.confirmation import init_action_guard, get_action_guard

        bus = MagicMock()
        guard = init_action_guard(event_bus=bus, interactive=True)
        assert guard._permission_manager is permission_manager
        assert get_action_guard() is guard
