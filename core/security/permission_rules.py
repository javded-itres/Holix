"""Declarative tool permissions: allow / ask / deny, last match wins.

Rules live in ``.holix/permissions.yaml`` (project) and
``<profile>/permissions.yaml`` (user). User rules are evaluated first, then
project rules, so a project rule can override a user rule.

A missing file leaves the existing ActionGuard policy unchanged.
"""

from __future__ import annotations

import fnmatch
import logging
import os
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

DECISIONS = ("allow", "ask", "deny")

_EDIT = frozenset({"write_file", "patch_file", "apply_patch", "notebook_edit", "delete_file"})
_BASH = frozenset(
    {
        "run_terminal_command",
        "terminal",
        "execute_terminal_command",
        "ssh_exec",
    }
)
_READ = frozenset({"read_file", "grep", "glob", "list_directory"})
_GROUPS = {"edit": _EDIT, "bash": _BASH, "read": _READ}

_NETWORK = (
    "curl",
    "wget",
    "nc",
    "ncat",
    "ssh",
    "scp",
    "rsync",
    "ping",
    "telnet",
    "ftp",
)

_decision: ContextVar[str | None] = ContextVar("holix_permission_rule", default=None)


@dataclass(frozen=True, slots=True)
class PermissionRule:
    tool: str
    decision: str
    path: str = ""
    command: str = ""


@dataclass(frozen=True, slots=True)
class PermissionPolicy:
    rules: tuple[PermissionRule, ...] = ()
    network: str = ""  # "" | "deny" | "allow"


def current_rule_decision() -> str | None:
    return _decision.get()


def rule_decision_scope(decision: str | None):
    return _decision.set(decision)


def reset_rule_decision(token) -> None:
    _decision.reset(token)


def _normalize_decision(raw: Any) -> str | None:
    text = str(raw or "").strip().lower()
    if text in DECISIONS:
        return text
    return None


def _as_rules(node: Any) -> list[PermissionRule]:
    if not isinstance(node, list):
        return []
    out: list[PermissionRule] = []
    for item in node:
        if not isinstance(item, dict):
            continue
        decision = _normalize_decision(item.get("decision") or item.get("action"))
        tool = str(item.get("tool") or item.get("name") or "").strip()
        if not decision or not tool:
            continue
        out.append(
            PermissionRule(
                tool=tool,
                decision=decision,
                path=str(item.get("path") or item.get("glob") or "").strip(),
                command=str(item.get("command") or "").strip(),
            )
        )
    return out


def parse_policy(payload: Any) -> PermissionPolicy:
    if not isinstance(payload, dict):
        return PermissionPolicy()
    rules = _as_rules(payload.get("rules"))
    sandbox = payload.get("sandbox")
    network = ""
    if isinstance(sandbox, dict):
        network = str(sandbox.get("network") or "").strip().lower()
        if network not in {"deny", "allow"}:
            network = ""
    return PermissionPolicy(rules=tuple(rules), network=network)


def load_policy_file(path: Path) -> PermissionPolicy:
    try:
        if not path.is_file():
            return PermissionPolicy()
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        logger.debug("permission rules unreadable: %s", path, exc_info=True)
        return PermissionPolicy()
    return parse_policy(payload)


def _merge(user: PermissionPolicy, project: PermissionPolicy) -> PermissionPolicy:
    network = project.network or user.network
    return PermissionPolicy(rules=user.rules + project.rules, network=network)


def load_policy(*, workspace: str | Path | None, profile: str | None) -> PermissionPolicy:
    project = PermissionPolicy()
    user = PermissionPolicy()
    if workspace:
        root = Path(workspace).expanduser()
        project = load_policy_file(root / ".holix" / "permissions.yaml")
    if profile:
        try:
            from core.profile.names import profile_dir_for_name

            user = load_policy_file(profile_dir_for_name(profile) / "permissions.yaml")
        except Exception:
            user = PermissionPolicy()
    return _merge(user, project)


def _tool_matches(rule: PermissionRule, tool_name: str) -> bool:
    key = (tool_name or "").strip()
    wanted = rule.tool.strip()
    if not key or not wanted:
        return False
    if wanted == "*":
        return True
    group = _GROUPS.get(wanted)
    if group is not None:
        return key in group
    return wanted == key


def _glob_ok(pattern: str, value: str) -> bool:
    if not pattern:
        return True
    return fnmatch.fnmatch(value.replace("\\", "/"), pattern)


def _argument_path(arguments: dict[str, Any] | None) -> str:
    args = arguments or {}
    for key in ("path", "file", "file_path", "target"):
        raw = args.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip().replace("\\", "/")
    return ""


def _argument_command(arguments: dict[str, Any] | None) -> str:
    args = arguments or {}
    raw = args.get("command")
    if isinstance(raw, str):
        return raw.strip()
    return ""


def _looks_network(command: str) -> bool:
    text = (command or "").strip()
    if not text:
        return False
    head = text.split()[0]
    base = head.rsplit("/", 1)[-1].lower()
    return base in _NETWORK


def evaluate(
    tool_name: str,
    arguments: dict[str, Any] | None,
    policy: PermissionPolicy,
) -> str | None:
    """Return allow, ask, deny, or None when no rule matches."""
    path = _argument_path(arguments)
    command = _argument_command(arguments)
    decision: str | None = None
    for rule in policy.rules:
        if not _tool_matches(rule, tool_name):
            continue
        if rule.path and not _glob_ok(rule.path, path or ""):
            continue
        if rule.command and not _glob_ok(rule.command, command or ""):
            continue
        decision = rule.decision
    if policy.network == "deny" and tool_name in _BASH and _looks_network(command):
        return "deny"
    return decision


def evaluate_for_call(
    tool_name: str,
    arguments: dict[str, Any] | None,
    *,
    workspace: str | Path | None,
    profile: str | None,
) -> str | None:
    if os.environ.get("HOLIX_PERMISSION_RULES", "1").strip().lower() in {
        "0",
        "off",
        "false",
        "no",
    }:
        return None
    policy = load_policy(workspace=workspace, profile=profile)
    if not policy.rules and not policy.network:
        return None
    return evaluate(tool_name, arguments, policy)
