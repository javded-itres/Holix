"""Session doctor spawn isolation and confirmed Telegram admin tickets."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from core.runtime.admin_support import (
    admin_ids_from_env,
    build_ticket_payload,
    deliver_admin_support_ticket,
    format_admin_html,
    infer_surface,
    parse_telegram_user_ids,
)
from core.security.confirmation import (
    ActionGuard,
    ConfirmationChoice,
    PermissionManager,
    PermissionScope,
    RiskClassifier,
    RiskLevel,
)
from core.subagents.registry import get_subagent_config
from core.subagents.spawn import prepare_subagent_config
from core.tools.registry import ToolRegistry
from core.tools.slot_policy import PLAN_MODE_BLOCKED, tool_allowed_for_slot


def test_parse_telegram_user_ids() -> None:
    assert parse_telegram_user_ids("1001, 1002 1002;1003") == [1001, 1002, 1003]
    assert parse_telegram_user_ids("") == []
    assert parse_telegram_user_ids("not-a-number") == []


def test_admin_ids_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLIX_TELEGRAM_ADMIN_USER_ID", "111")
    monkeypatch.setenv("HOLIX_TELEGRAM_ADMIN_EXTRA_USER_IDS", "222,111,333")
    assert admin_ids_from_env() == [111, 222, 333]


def test_infer_surface() -> None:
    assert infer_surface("tg_shared_1_99") == "telegram"
    assert infer_surface("max_production_1") == "max"
    assert infer_surface("subagent:abc:session_doctor-1") == "subagent"
    assert infer_surface("default") == "local"


def test_session_doctor_builtin_is_isolated() -> None:
    cfg = get_subagent_config("session_doctor")
    assert cfg.fork is False
    assert cfg.mcp_inherit is False
    assert cfg.memory_access.value == "isolated"
    assert "self_diagnose" in cfg.tools
    assert "request_admin_support" in cfg.tools
    assert "ask_user" in cfg.tools
    assert "write_file" not in cfg.tools
    assert "run_terminal_command" not in cfg.tools
    assert "manage_agent_extensions" not in cfg.tools
    assert "tool_search" not in cfg.tools
    assert "delegate_to_subagent" not in cfg.tools


def test_prepare_session_doctor_keeps_readonly_tools() -> None:
    parent = SimpleNamespace(
        profile_name="default",
        subagent_default_process_mode="async",
        subagent_process_timeout=30.0,
        mcp_assignments={},
        agent_models={},
    )
    doctor = prepare_subagent_config("session_doctor", parent, instance_name="session_doctor-1")
    assert doctor.fork is False
    assert doctor.mcp_inherit is False
    assert doctor.memory_access.value == "isolated"
    assert "tool_search" not in doctor.tools
    assert "write_file" not in doctor.tools
    assert "self_diagnose" in doctor.tools
    assert "request_admin_support" in doctor.tools
    assert "ask_user" in doctor.tools


def test_request_admin_support_registered_and_confirms() -> None:
    registry = ToolRegistry(profile_name="default")
    registry.register_all()
    tool = registry.tools["request_admin_support"]
    assert tool.risk_level == "high"
    assert tool.require_user_confirmation is True
    assert tool_allowed_for_slot("request_admin_support", "session_doctor")
    assert "request_admin_support" in PLAN_MODE_BLOCKED


def test_ticket_payload_redacts_secrets() -> None:
    payload = build_ticket_payload(
        summary="Bot ignored a file",
        analysis="Inbound caption race",
        needed_settings="Check telegram host",
        conversation_id="tg_shared_1",
        profile="default",
        diagnose_report={
            "findings": [{"code": "tool_failures", "api_key": "sk-secret"}],
            "session": {"last_real_ask": "пришли файл", "tools": ["read_file"]},
            "llm": {"models": {"gpt-test": 2}},
        },
        logs=[{"type": "error", "token": "abc", "message": "fail"}],
    )
    assert payload["surface"] == "telegram"
    assert payload["model"] == "gpt-test"
    html = format_admin_html(payload)
    assert "Holix support" in html
    assert "tg_shared_1" in html
    dumped = str(payload)
    assert "sk-secret" not in dumped
    assert payload["findings"][0]["api_key"] == "***"
    assert payload["logs"][0]["token"] == "***"


@pytest.mark.asyncio
async def test_deliver_skips_when_no_admins(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.plugins.hooks import notify_hooks

    monkeypatch.delenv("HOLIX_TELEGRAM_ADMIN_USER_ID", raising=False)
    monkeypatch.delenv("HOLIX_TELEGRAM_ADMIN_EXTRA_USER_IDS", raising=False)
    notify_hooks.list_telegram_admins = None
    notify_hooks.send_telegram = None
    result = await deliver_admin_support_ticket(
        build_ticket_payload(summary="x", analysis="y", conversation_id="c1", profile="default")
    )
    assert result["ok"] is False
    assert result["code"] == "no_telegram_admin"
    assert result["sent"] == 0


@pytest.mark.asyncio
async def test_deliver_sends_to_all_admins(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.plugins.hooks import notify_hooks

    sent_text: list[int] = []
    sent_docs: list[int] = []

    async def send_telegram(chat_id, message, **kwargs):
        sent_text.append(int(chat_id))
        assert "Holix support" in message
        return True

    async def send_doc(chat_id, **kwargs):
        sent_docs.append(int(chat_id))
        assert kwargs.get("filename", "").endswith(".json")
        assert kwargs.get("content")
        return True

    prev_list = notify_hooks.list_telegram_admins
    prev_send = notify_hooks.send_telegram
    prev_doc = notify_hooks.send_telegram_document
    notify_hooks.list_telegram_admins = lambda profile: [
        {"profile": "shared", "user_id": 10},
        {"profile": "shared", "user_id": 20},
    ]
    notify_hooks.send_telegram = send_telegram
    notify_hooks.send_telegram_document = send_doc
    try:
        result = await deliver_admin_support_ticket(
            build_ticket_payload(summary="x", analysis="y", conversation_id="tg_a", profile="u1")
        )
        assert result["ok"] is True
        assert result["sent"] == 2
        assert sent_text == [10, 20]
        assert sent_docs == [10, 20]
    finally:
        notify_hooks.list_telegram_admins = prev_list
        notify_hooks.send_telegram = prev_send
        notify_hooks.send_telegram_document = prev_doc


@pytest.mark.asyncio
async def test_require_user_confirmation_denies_without_execute() -> None:
    pm = PermissionManager()
    guard = ActionGuard(
        event_bus=None,
        permission_manager=pm,
        risk_classifier=RiskClassifier(),
        auto_allow_threshold=RiskLevel.HIGH,
        interactive=False,
    )

    class FakeTool:
        risk_level = "high"
        require_user_confirmation = True

    executed = {"n": 0}

    async def fake_execute(**kwargs):
        executed["n"] += 1
        return "sent"

    result = await guard.check_and_execute(
        tool_name="request_admin_support",
        tool_instance=FakeTool(),
        arguments={"summary": "x", "analysis": "y"},
        execute_fn=fake_execute,
    )
    assert executed["n"] == 0
    assert "denied" in result.lower() or "confirmation" in result.lower()
    assert (
        "Nothing was sent" in result
        or "not sent" in result.lower()
        or "confirmation" in result.lower()
    )


@pytest.mark.asyncio
async def test_require_user_confirmation_ignores_stored_grant() -> None:
    import asyncio
    import tempfile
    from pathlib import Path

    fd, path = tempfile.mkstemp(suffix=".json")
    import os

    os.close(fd)
    pm = PermissionManager()
    pm.PERMISSIONS_FILE = Path(path)
    pm.grant("request_admin_support", PermissionScope.ALWAYS, RiskLevel.HIGH)
    guard = ActionGuard(
        event_bus=None,
        permission_manager=pm,
        risk_classifier=RiskClassifier(),
        auto_allow_threshold=RiskLevel.NO,
        interactive=True,
        confirmation_timeout=5,
    )

    class FakeTool:
        risk_level = "high"
        require_user_confirmation = True

    executed = {"n": 0}

    async def fake_execute(**kwargs):
        executed["n"] += 1
        return "sent"

    task = asyncio.create_task(
        guard.check_and_execute(
            tool_name="request_admin_support",
            tool_instance=FakeTool(),
            arguments={"summary": "x", "analysis": "y"},
            execute_fn=fake_execute,
            conversation_id="test",
        )
    )
    await asyncio.sleep(0.05)
    assert len(guard._pending_confirmations) == 1
    cid = list(guard._pending_confirmations.keys())[0]
    guard.resolve_confirmation(cid, ConfirmationChoice.DENY)
    result = await asyncio.wait_for(task, timeout=5.0)
    assert executed["n"] == 0
    assert "denied" in result.lower()
    Path(path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_require_user_confirmation_allow_once_does_not_persist() -> None:
    import asyncio
    import os
    import tempfile
    from pathlib import Path

    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    pm = PermissionManager()
    pm.PERMISSIONS_FILE = Path(path)
    guard = ActionGuard(
        event_bus=None,
        permission_manager=pm,
        risk_classifier=RiskClassifier(),
        auto_allow_threshold=RiskLevel.NO,
        interactive=True,
        confirmation_timeout=5,
    )

    class FakeTool:
        risk_level = "high"
        require_user_confirmation = True

    async def fake_execute(**kwargs):
        return "sent"

    task = asyncio.create_task(
        guard.check_and_execute(
            tool_name="request_admin_support",
            tool_instance=FakeTool(),
            arguments={"summary": "x", "analysis": "y"},
            execute_fn=fake_execute,
            conversation_id="test",
        )
    )
    await asyncio.sleep(0.05)
    cid = list(guard._pending_confirmations.keys())[0]
    guard.resolve_confirmation(cid, ConfirmationChoice.ALLOW_ALWAYS)
    result = await asyncio.wait_for(task, timeout=5.0)
    assert result == "sent"
    assert not pm.is_allowed("request_admin_support", RiskLevel.HIGH)
    Path(path).unlink(missing_ok=True)
