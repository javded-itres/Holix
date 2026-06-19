"""
Confirmation System — dangerous action confirmation for Holix tools.

Provides risk classification, permission management, and interactive
confirmation prompts before executing high-risk tool calls.

Architecture:
    Tool Call → ToolRegistry.execute()
      → ActionGuard.check_and_execute()
        → RiskClassifier.classify() → RiskAssessment
        → if auto-allowed (≤ threshold): execute directly
        → if PermissionManager.is_allowed(): execute directly
        → else: emit ConfirmationRequestEvent → await Future
             ← TUI/API resolves via resolve_confirmation()
        → execute or deny
"""

import asyncio
import json
import logging
import re
import threading
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ─── Risk Levels ──────────────────────────────────────────────────────────

class RiskLevel(StrEnum):
    """Risk classification for tool calls."""
    NO = "no"          # Safe: read-only, no side effects
    LOW = "low"        # Minor side effects: network reads
    MEDIUM = "medium"  # Destructive potential: file writes, SQL mutations
    HIGH = "high"      # Unrestricted: shell commands, code execution


# Ordering for comparison: NO < LOW < MEDIUM < HIGH
_RISK_ORDER = {RiskLevel.NO: 0, RiskLevel.LOW: 1, RiskLevel.MEDIUM: 2, RiskLevel.HIGH: 3}


@dataclass
class RiskAssessment:
    """Result of risk classification for a tool call."""
    risk_level: RiskLevel = RiskLevel.MEDIUM
    reason: str = ""
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    pattern_matched: str | None = None  # Which escalation pattern triggered, if any


# ─── Risk Classifier ──────────────────────────────────────────────────────

class RiskClassifier:
    """Classifies tool calls by risk level.

    Uses a two-stage approach:
    1. Declarative: the tool class declares its baseline risk_level.
    2. Argument analysis: specific argument patterns can escalate risk.

    Reuses the existing ConfirmationRequired patterns from safety.py
    for terminal command analysis.
    """

    def __init__(self):
        # Import lazily to avoid circular imports at module level
        from core.security.safety import ConfirmationRequired
        self._confirmation_checker = ConfirmationRequired()

        # Sensitive file path patterns that escalate write_file to HIGH
        self._sensitive_path_patterns = [
            (r"config\.py$", "Writing to config.py"),
            (r"settings\.py$", "Writing to settings.py"),
            (r"/etc/", "Writing to /etc/"),
            (r"\.ssh/", "Writing to .ssh/"),
            (r"\.gnupg/", "Writing to .gnupg/"),
            (r"\.git/", "Writing to .git/ directory"),
            (r"id_rsa", "Writing to SSH private key"),
            (r"authorized_keys", "Writing to SSH authorized_keys"),
        ]

        # SQL mutation keywords that escalate sql_query to HIGH
        self._sql_mutation_keywords = {"INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE"}

    def classify(self, tool_name: str, tool_instance: Any, arguments: dict[str, Any]) -> RiskAssessment:
        """Classify a tool call by risk level.

        Args:
            tool_name: Name of the tool being called.
            tool_instance: The tool object (may have a risk_level attribute).
            arguments: The arguments dict being passed to the tool.

        Returns:
            RiskAssessment with level, reason, and escalation details.
        """
        # Stage 1: Declarative baseline from tool class
        baseline_str = getattr(tool_instance, "risk_level", "medium")
        try:
            baseline = RiskLevel(baseline_str)
        except ValueError:
            baseline = RiskLevel.MEDIUM

        # Stage 2: Argument-level escalation for specific tools
        escalated_level, escalation_reason, pattern = self._analyze_arguments(
            tool_name, arguments, baseline
        )

        return RiskAssessment(
            risk_level=escalated_level,
            reason=escalation_reason,
            tool_name=tool_name,
            arguments=arguments,
            pattern_matched=pattern,
        )

    def _analyze_arguments(
        self, tool_name: str, arguments: dict[str, Any], baseline: RiskLevel
    ) -> tuple:
        """Analyze tool arguments for risk escalation patterns.

        Returns:
            Tuple of (escalated_risk_level, reason, matched_pattern).
        """
        if tool_name in ("start_background_process", "run_project", "restart_background_process"):
            return RiskLevel.LOW, "Controlled background dev-server launcher", None

        if tool_name in (
            "check_background_process",
            "list_background_processes",
        ):
            return RiskLevel.LOW, "Background process status check", None

        if tool_name == "stop_background_process":
            return RiskLevel.LOW, "Stop background dev server", None

        # TerminalTool: always HIGH, but check for blocked patterns
        if tool_name == "run_terminal_command":
            command = arguments.get("command", "")
            # Check dangerous patterns from ConfirmationRequired
            if self._confirmation_checker.requires_confirmation(command):
                return RiskLevel.HIGH, f"Dangerous terminal command: {command[:60]}", "terminal_dangerous_pattern"
            return RiskLevel.HIGH, "Terminal command execution", None

        # PythonExecutorTool: always HIGH
        if tool_name == "execute_python":
            code = arguments.get("code", "")
            # Check for especially dangerous patterns in code
            dangerous_patterns = [
                (r"import\s+os\b", "OS module import"),
                (r"import\s+subprocess\b", "Subprocess module import"),
                (r"os\.system\(", "os.system() call"),
                (r"subprocess\.", "Subprocess call"),
                (r"open\(.+[\"']w[\"']", "File write in code"),
                (r"shutil\.rmtree", "Directory removal"),
                (r"os\.remove\(", "File removal"),
            ]
            for pattern, reason in dangerous_patterns:
                if re.search(pattern, code):
                    return RiskLevel.HIGH, f"Dangerous code pattern: {reason}", f"code_dangerous:{pattern}"
            return RiskLevel.HIGH, "Python code execution (exec/eval)", None

        # WriteFileTool: escalate if writing to sensitive paths
        if tool_name == "write_file":
            path = arguments.get("path", "")
            if self._is_env_file_path(path):
                if self._is_holix_env_path(path):
                    return (
                        RiskLevel.HIGH,
                        "Writing to Holix profile .env file",
                        "write_sensitive_path:holix_env",
                    )
                return RiskLevel.LOW, "Project .env setup", None
            for pattern, reason in self._sensitive_path_patterns:
                if re.search(pattern, path):
                    return RiskLevel.HIGH, reason, f"write_sensitive_path:{pattern}"
            return RiskLevel.MEDIUM, "File write operation", None

        # SQLQueryTool: escalate if non-SELECT
        if tool_name == "sql_query":
            query = arguments.get("query", "").strip()
            query_type = query.split()[0].upper() if query else ""
            if query_type in self._sql_mutation_keywords:
                return RiskLevel.HIGH, f"SQL mutation: {query_type}", "sql_mutation"
            return RiskLevel.MEDIUM, "SQL query", None

        # SQLSchemaTool: read-only
        if tool_name == "sql_schema":
            return RiskLevel.NO, "Schema inspection (read-only)", None

        # WebFetchTool: POST is more dangerous than GET
        if tool_name in ("fetch_url", "web_fetch"):
            method = arguments.get("method", "GET").upper()
            if method == "POST":
                return RiskLevel.MEDIUM, "HTTP POST request", "web_post_method"
            return RiskLevel.LOW, "HTTP GET request", None

        # ReadFileTool, ListDirectoryTool: always NO
        if tool_name in ("read_file", "list_directory"):
            return RiskLevel.NO, "Read-only operation", None

        # WebSearchTool: always LOW
        if tool_name == "web_search":
            return RiskLevel.LOW, "Web search (read-only)", None

        # MathCalculatorTool: always NO
        if tool_name == "calculate":
            return RiskLevel.NO, "Pure calculation", None

        # Default: use the declarative baseline
        return baseline, f"Tool: {tool_name}", None

    @staticmethod
    def _is_env_file_path(path: str) -> bool:
        name = Path(path).name
        return name == ".env" or name.startswith(".env.")

    @staticmethod
    def _resolve_write_path(path: str) -> Path | None:
        raw = Path(path).expanduser()
        try:
            if raw.is_absolute():
                return raw.resolve()
            return (Path.cwd() / raw).resolve()
        except OSError:
            return None

    def _is_holix_env_path(self, path: str) -> bool:
        if not self._is_env_file_path(path):
            return False
        resolved = self._resolve_write_path(path)
        if resolved is None:
            return False
        from core.env_loader import holix_home

        try:
            resolved.relative_to(holix_home().resolve())
        except ValueError:
            return False
        return True


# ─── Permission Management ────────────────────────────────────────────────

class PermissionScope(StrEnum):
    """How long a permission grant lasts."""
    ONCE = "once"          # Only this invocation (not stored)
    SESSION = "session"    # Until the agent process exits
    ALWAYS = "always"      # Persisted across restarts


@dataclass
class PermissionGrant:
    """A stored permission decision."""
    tool_name: str
    scope: PermissionScope
    risk_level: RiskLevel
    argument_pattern: str | None = None
    granted_at: str = ""


class PermissionManager:
    """Manages permission grants for tool calls.

    Stores session-scoped grants in memory and persistent grants in
    a JSON file. Thread-safe via a lock.
    """

    def __init__(self, data_dir: str | Path | None = None):
        self._data_dir: Path | None = (
            Path(data_dir).expanduser().resolve() if data_dir is not None else None
        )
        self._permissions_file_override: Path | None = None
        self._session_grants: dict[str, PermissionGrant] = {}
        self._always_grants: dict[str, PermissionGrant] = {}
        self._lock = threading.Lock()
        self._loaded = False

    def set_data_dir(self, data_dir: str | Path) -> None:
        """Point storage at the active profile data directory."""
        self._data_dir = Path(data_dir).expanduser().resolve()
        self._permissions_file_override = None

    @property
    def data_dir(self) -> Path:
        if self._data_dir is not None:
            return self._data_dir
        from core.paths import resolve_profile_data_dir

        return resolve_profile_data_dir()

    @property
    def PERMISSIONS_FILE(self) -> Path:
        if self._permissions_file_override is not None:
            return self._permissions_file_override
        return self.data_dir / "security" / "permissions.json"

    @PERMISSIONS_FILE.setter
    def PERMISSIONS_FILE(self, value: Path) -> None:
        self._permissions_file_override = Path(value)

    @property
    def audit_log_path(self) -> Path:
        return self.data_dir / "security" / "confirmation_audit.jsonl"

    @staticmethod
    def _grant_key(tool_name: str, risk_level: RiskLevel, argument_pattern: str | None = None) -> str:
        """Create a unique key for a permission grant."""
        if argument_pattern:
            return f"{tool_name}:{risk_level.value}:{argument_pattern}"
        return f"{tool_name}:{risk_level.value}"

    def load(self) -> None:
        """Load persistent grants from disk."""
        self._always_grants.clear()
        if self.PERMISSIONS_FILE.exists():
            try:
                data = json.loads(self.PERMISSIONS_FILE.read_text())
                for grant_data in data.get("always_grants", []):
                    risk_level = RiskLevel(grant_data["risk_level"])
                    grant = PermissionGrant(
                        tool_name=grant_data["tool_name"],
                        scope=PermissionScope.ALWAYS,
                        risk_level=risk_level,
                        argument_pattern=grant_data.get("argument_pattern"),
                        granted_at=grant_data.get("granted_at", ""),
                    )
                    key = self._grant_key(grant.tool_name, grant.risk_level, grant.argument_pattern)
                    self._always_grants[key] = grant
            except Exception:
                pass  # Corrupt file: start fresh
        self._loaded = True

    def save(self) -> None:
        """Persist 'always' grants to disk."""
        self.PERMISSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "always_grants": [
                {
                    "tool_name": g.tool_name,
                    "risk_level": g.risk_level.value,
                    "argument_pattern": g.argument_pattern,
                    "granted_at": g.granted_at,
                }
                for g in self._always_grants.values()
            ]
        }
        self.PERMISSIONS_FILE.write_text(json.dumps(data, indent=2))

    def is_allowed(self, tool_name: str, risk_level: RiskLevel, argument_pattern: str | None = None) -> bool:
        """Check if a tool call is pre-authorized by a session or persistent grant.

        For ALWAYS grants, also matches if the granted level is >= the requested level
        (e.g., a HIGH grant also covers MEDIUM for the same tool).
        """
        self._ensure_loaded()
        key = self._grant_key(tool_name, risk_level, argument_pattern)
        with self._lock:
            if key in self._session_grants or key in self._always_grants:
                return True

            # Also check broader grants (same tool, higher granted risk level)
            for granted_key, grant in {**self._session_grants, **self._always_grants}.items():
                if grant.tool_name == tool_name:
                    # If we have a grant for this tool at a higher risk level, it covers lower ones
                    if _RISK_ORDER.get(grant.risk_level, 0) >= _RISK_ORDER.get(risk_level, 0):
                        # But only if the argument pattern matches or is broader
                        if grant.argument_pattern is None or grant.argument_pattern == argument_pattern:
                            return True

            return False

    def grant(self, tool_name: str, scope: PermissionScope, risk_level: RiskLevel,
              argument_pattern: str | None = None) -> None:
        """Record a permission grant."""
        self._ensure_loaded()
        grant = PermissionGrant(
            tool_name=tool_name,
            scope=scope,
            risk_level=risk_level,
            argument_pattern=argument_pattern,
            granted_at=datetime.now().isoformat(),
        )
        key = self._grant_key(tool_name, risk_level, argument_pattern)
        with self._lock:
            if scope == PermissionScope.SESSION:
                self._session_grants[key] = grant
            elif scope == PermissionScope.ALWAYS:
                self._always_grants[key] = grant
                self.save()
            # ONCE is not stored — it only applies to the current invocation

    def revoke(self, tool_name: str, scope: PermissionScope, risk_level: RiskLevel,
               argument_pattern: str | None = None) -> None:
        """Revoke a permission grant."""
        self._ensure_loaded()
        key = self._grant_key(tool_name, risk_level, argument_pattern)
        with self._lock:
            if scope == PermissionScope.SESSION:
                self._session_grants.pop(key, None)
            elif scope == PermissionScope.ALWAYS:
                self._always_grants.pop(key, None)
                self.save()

    def clear_session(self) -> None:
        """Clear all session-scoped grants (called on agent shutdown)."""
        with self._lock:
            self._session_grants.clear()

    def list_grants(self) -> dict[str, Any]:
        """List all active grants for display in UI."""
        self._ensure_loaded()
        with self._lock:
            session = [
                {"tool": g.tool_name, "scope": "session", "risk": g.risk_level.value, "pattern": g.argument_pattern}
                for g in self._session_grants.values()
            ]
            always = [
                {"tool": g.tool_name, "scope": "always", "risk": g.risk_level.value, "pattern": g.argument_pattern}
                for g in self._always_grants.values()
            ]
        return {"session": session, "always": always}

    def _ensure_loaded(self) -> None:
        """Lazy-load persistent grants on first access."""
        if not self._loaded:
            self.load()


# Shared instance: ActionGuard, gateway /v1/permissions/*, and TUI all use this.
permission_manager = PermissionManager()


# ─── Confirmation Choice ──────────────────────────────────────────────────

class ConfirmationChoice(StrEnum):
    """User choices for a confirmation request."""
    ALLOW_ONCE = "allow_once"        # Allow this one invocation only
    ALLOW_SESSION = "allow_session"  # Allow for the rest of this session
    ALLOW_ALWAYS = "allow_always"    # Persist permission
    DENY = "deny"                    # Block this tool call


def normalize_confirmation_timeout(value: int | float | None, *, default: int = 0) -> int:
    """Seconds to wait for user approval. 0 or negative = no timeout."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ─── Action Guard ──────────────────────────────────────────────────────────

class ActionGuard:
    """Intercepts tool calls and enforces confirmation policy.

    The guard is the single point where tool execution is authorized.
    It uses RiskClassifier to assess risk, PermissionManager to check
    stored grants, and (when needed) emits ConfirmationRequestEvent
    to the event bus and awaits a response via asyncio.Future.

    For non-interactive (API) contexts, it uses an auto-deny/auto-allow
    policy based on config thresholds.
    """

    def __init__(
        self,
        event_bus: Any | None = None,
        permission_manager: PermissionManager | None = None,
        risk_classifier: RiskClassifier | None = None,
        auto_allow_threshold: RiskLevel = RiskLevel.LOW,
        interactive: bool = True,
        confirmation_timeout: int = 0,
        data_dir: str | Path | None = None,
    ):
        self._event_bus = event_bus
        self._permission_manager = permission_manager or PermissionManager(
            data_dir=data_dir
        )
        self._risk_classifier = risk_classifier or RiskClassifier()
        if data_dir is not None:
            self._audit_log_path = Path(data_dir).expanduser().resolve() / "security" / "confirmation_audit.jsonl"
        else:
            self._audit_log_path = self._permission_manager.audit_log_path
        self._auto_allow_threshold = auto_allow_threshold
        self._interactive = interactive
        self._confirmation_timeout = confirmation_timeout

        # Map from confirmation_id -> asyncio.Future[ConfirmationChoice]
        self._pending_confirmations: dict[str, asyncio.Future] = {}
        self._confirmation_counter = 0

        # Audit logging callback
        self._audit_logger: Callable | None = None

        # When True, all tool calls are auto-approved without confirmation.
        # Set when a confirmed plan is being executed, so tools within
        # plan steps don't require individual confirmation.
        self._auto_approve_plan_execution: bool = False
        # Gateway cron / other headless runs (no TUI to confirm).
        self._auto_approve_background: bool = False

    def set_audit_logger(self, logger_fn: Callable) -> None:
        """Set a function that receives audit records for every confirmation decision."""
        self._audit_logger = logger_fn

    @asynccontextmanager
    async def background_auto_approve(self):
        """Allow tool calls without TUI confirmation (gateway cron, etc.)."""
        self._auto_approve_background = True
        try:
            yield
        finally:
            self._auto_approve_background = False

    async def check_and_execute(
        self,
        tool_name: str,
        tool_instance: Any,
        arguments: dict[str, Any],
        execute_fn: Callable,
        conversation_id: str = "default",
    ) -> str:
        """Main entry point: classify, check permissions, confirm if needed, then execute.

        Args:
            tool_name: Name of the tool.
            tool_instance: The tool object (for risk_level attribute).
            arguments: Arguments dict for the tool call.
            execute_fn: Async callable that actually runs the tool.
            conversation_id: Conversation ID for event correlation.

        Returns:
            The tool's result string, or a denial message.
        """
        # Step 1: Classify risk
        assessment = self._risk_classifier.classify(tool_name, tool_instance, arguments)

        # Step 1.5: Headless / plan execution — skip confirmation prompts
        if self._auto_approve_background:
            self._log_audit("auto_approved_background", assessment, "background_run")
            return await execute_fn(**arguments)
        if self._auto_approve_plan_execution:
            self._log_audit("auto_approved_plan_execution", assessment, "plan_execution_mode")
            return await execute_fn(**arguments)

        # Step 2: Check if auto-allowed by config threshold
        if _RISK_ORDER.get(assessment.risk_level, 0) <= _RISK_ORDER.get(self._auto_allow_threshold, 1):
            self._log_audit("auto_allowed", assessment, "below_threshold")
            return await execute_fn(**arguments)

        # Step 3: Check stored permissions
        if self._permission_manager.is_allowed(
            tool_name, assessment.risk_level, assessment.pattern_matched
        ):
            self._log_audit("permission_granted", assessment, "stored")
            return await execute_fn(**arguments)

        # Step 4: Need confirmation
        if not self._interactive:
            # Non-interactive mode: auto-deny
            self._log_audit("auto_denied", assessment, "non_interactive")
            return (
                f"Error: Tool '{tool_name}' requires confirmation but running in non-interactive mode. "
                f"Reason: {assessment.reason}. "
                f"Use /v1/permissions/grant API to pre-authorize, or set auto_allow_threshold higher."
            )

        # Step 5: Emit confirmation request event and await response
        choice = await self._request_confirmation(assessment, conversation_id)

        if choice == ConfirmationChoice.DENY:
            self._log_audit("denied", assessment, "user_deny")
            return f"Error: Tool call '{tool_name}' denied by user. Reason: {assessment.reason}"

        # Step 6: Record grant
        scope_map = {
            ConfirmationChoice.ALLOW_ONCE: PermissionScope.ONCE,
            ConfirmationChoice.ALLOW_SESSION: PermissionScope.SESSION,
            ConfirmationChoice.ALLOW_ALWAYS: PermissionScope.ALWAYS,
        }
        scope = scope_map[choice]
        self._permission_manager.grant(
            tool_name, scope, assessment.risk_level, assessment.pattern_matched
        )
        self._log_audit("allowed", assessment, f"user_{choice.value}")

        # Step 7: Execute
        return await execute_fn(**arguments)

    async def _request_confirmation(
        self, assessment: RiskAssessment, conversation_id: str
    ) -> ConfirmationChoice:
        """Emit a ConfirmationRequestEvent and await resolution.

        Creates an asyncio.Future, stores it, emits the event,
        and awaits the result. The TUI or API layer resolves it
        by calling resolve_confirmation().
        """
        self._confirmation_counter += 1
        confirmation_id = f"confirm_{self._confirmation_counter}_{conversation_id}"

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending_confirmations[confirmation_id] = future

        logger.info(
            f"ActionGuard: requesting confirmation for {assessment.tool_name} "
            f"(risk={assessment.risk_level.value}, id={confirmation_id})"
        )

        try:
            # Emit the event for TUI/API consumption
            if self._event_bus:
                from core.security.confirmation_events import ConfirmationRequestEvent
                from core.tools.execution_context import get_subagent_name

                subagent_name = get_subagent_name()
                event = ConfirmationRequestEvent(
                    confirmation_id=confirmation_id,
                    tool_name=assessment.tool_name,
                    arguments=assessment.arguments,
                    risk_level=assessment.risk_level.value,
                    reason=assessment.reason,
                    pattern_matched=assessment.pattern_matched,
                    conversation_id=conversation_id,
                    subagent_name=subagent_name,
                )
                self._event_bus.emit(event)
                logger.info(f"ActionGuard: emitted ConfirmationRequestEvent (id={confirmation_id})")

            # Wait for resolution (with configurable timeout)
            timeout = self._confirmation_timeout if self._confirmation_timeout > 0 else None
            logger.info(f"ActionGuard: awaiting confirmation (timeout={timeout}s)")
            return await asyncio.wait_for(future, timeout=timeout)

        except TimeoutError:
            # Timeout = deny
            self._log_audit("timeout", assessment, "confirmation_timeout")
            return ConfirmationChoice.DENY

        finally:
            self._pending_confirmations.pop(confirmation_id, None)

    def resolve_confirmation(self, confirmation_id: str, choice: ConfirmationChoice) -> bool:
        """Resolve a pending confirmation request.

        Called by the TUI or API layer when the user responds to
        a confirmation prompt. Returns True if successfully resolved,
        False if the ID was not found (e.g., already timed out).
        """
        future = self._pending_confirmations.get(confirmation_id)
        if future is None or future.done():
            return False

        future.set_result(choice)

        # Emit response event for logging/UI feedback
        if self._event_bus:
            from core.security.confirmation_events import ConfirmationResponseEvent
            self._event_bus.emit(ConfirmationResponseEvent(
                confirmation_id=confirmation_id,
                choice=choice.value,
                conversation_id="",
            ))

        return True

    def _log_audit(self, action: str, assessment: RiskAssessment, detail: str | None) -> None:
        """Log an audit record to file and optional callback."""
        record = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "tool_name": assessment.tool_name,
            "risk_level": assessment.risk_level.value,
            "reason": assessment.reason,
            "pattern_matched": assessment.pattern_matched,
            "detail": detail,
        }
        logger.info(f"ActionGuard: {action} for {assessment.tool_name} (risk={assessment.risk_level.value})")

        # Write to audit log file
        try:
            audit_log = self._audit_log_path
            audit_log.parent.mkdir(parents=True, exist_ok=True)
            with open(audit_log, "a") as f:
                f.write(json.dumps(record) + "\n")
        except Exception:
            logger.warning("Could not write to confirmation audit log")

        if self._audit_logger:
            self._audit_logger(record)


# ─── Global instance and init ──────────────────────────────────────────────

_action_guard: ActionGuard | None = None
_profile_action_guards: dict[str, ActionGuard] = {}
_profile_permission_managers: dict[str, PermissionManager] = {}


def configure_security_storage(data_dir: str | Path) -> None:
    """Bind global permission storage to the active profile data directory."""
    permission_manager.set_data_dir(data_dir)


def init_action_guard(
    event_bus: Any,
    auto_allow_threshold: RiskLevel = RiskLevel.LOW,
    interactive: bool = True,
    confirmation_timeout: int = 0,
    data_dir: str | Path | None = None,
    profile_name: str | None = None,
) -> ActionGuard:
    """Initialize the global ActionGuard instance.

    Called by HolixAgent after the event bus is ready.
    """
    global _action_guard
    profile_key = (profile_name or "").strip() or None
    if data_dir is not None and profile_key:
        pm = PermissionManager(data_dir=data_dir)
        _profile_permission_managers[profile_key] = pm
    elif data_dir is not None:
        configure_security_storage(data_dir)
        pm = permission_manager
    else:
        pm = permission_manager

    guard = ActionGuard(
        event_bus=event_bus,
        permission_manager=pm,
        auto_allow_threshold=auto_allow_threshold,
        interactive=interactive,
        confirmation_timeout=confirmation_timeout,
        data_dir=data_dir,
    )
    if profile_key:
        _profile_action_guards[profile_key] = guard
    _action_guard = guard
    return guard


def get_action_guard(profile_name: str | None = None) -> ActionGuard | None:
    """Get ActionGuard for a profile, or the last-initialized global guard."""
    profile_key = (profile_name or "").strip() or None
    if profile_key:
        return _profile_action_guards.get(profile_key) or _action_guard
    return _action_guard


def get_permission_manager_for_profile(profile_name: str) -> PermissionManager:
    """Return the permission store scoped to a profile."""
    profile_key = (profile_name or "").strip() or "default"
    existing = _profile_permission_managers.get(profile_key)
    if existing is not None:
        return existing
    from core.paths import resolve_profile_data_dir

    pm = PermissionManager(data_dir=resolve_profile_data_dir(profile_key))
    _profile_permission_managers[profile_key] = pm
    return pm