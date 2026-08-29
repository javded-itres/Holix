"""Unit tests for coding-agent tools (apply_patch, aliases, plan_mode, …)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from core.tools.aliases import infer_alias_action, resolve_tool_name
from core.tools.apply_patch import ApplyPatchTool, extract_apply_patch_document
from core.tools.ask_user import AskUserTool, normalize_ask_user_args
from core.tools.base import filter_execute_kwargs
from core.tools.execution_context import (
    conversation_scope,
    profile_scope,
    reset_conversation_scope,
    reset_profile_scope,
    reset_subagent_scope,
    reset_tools_registry_scope,
    reset_workspace_scope,
    subagent_scope,
    tools_registry_scope,
    workspace_scope,
)
from core.tools.job_monitor import JobMonitorTool
from core.tools.notebook_edit import NotebookEditTool
from core.tools.plan_mode import PlanModeTool
from core.tools.plan_mode_state import exit_plan_mode
from core.tools.registry import ToolRegistry
from core.tools.subagent_control import SubagentControlTool
from core.tools.tool_search import ToolSearchTool


def _call(name: str, **kwargs):
    return SimpleNamespace(
        id="c1",
        type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(kwargs, ensure_ascii=False)),
    )


def _patch_doc(*ops: str) -> str:
    body = "\n".join(ops)
    return f"*** Begin Patch\n{body}\n*** End Patch\n"


@pytest.mark.asyncio
async def test_apply_patch_add_update_delete(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.py").write_text("x = 1\n", encoding="utf-8")
    (ws / "gone.py").write_text("bye\n", encoding="utf-8")
    tokens = workspace_scope(workspace_root=str(ws), workspace_jail_enabled=True)
    try:
        result = await ApplyPatchTool().execute(
            patch=_patch_doc(
                "*** Add File: new.py",
                "+hello",
                "*** Update File: a.py",
                "@@",
                "-x = 1",
                "+x = 2",
                "*** Delete File: gone.py",
            )
        )
        payload = json.loads(result)
        assert payload["ok"] is True
        actions = {row["path"]: row["action"] for row in payload["files"]}
        assert actions["new.py"] == "add"
        assert actions["a.py"] == "update"
        assert actions["gone.py"] == "delete"
        assert (ws / "new.py").read_text(encoding="utf-8") == "hello\n"
        assert (ws / "a.py").read_text(encoding="utf-8") == "x = 2\n"
        assert not (ws / "gone.py").exists()
    finally:
        reset_workspace_scope(tokens)


@pytest.mark.asyncio
async def test_apply_patch_hunk_mismatch_does_not_write(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    target = ws / "a.py"
    target.write_text("x = 1\n", encoding="utf-8")
    tokens = workspace_scope(workspace_root=str(ws), workspace_jail_enabled=True)
    try:
        result = await ApplyPatchTool().execute(
            patch=_patch_doc(
                "*** Update File: a.py",
                "@@",
                "-x = 99",
                "+x = 2",
            )
        )
        payload = json.loads(result)
        assert payload["ok"] is False
        assert payload["code"] == "hunk_mismatch"
        assert target.read_text(encoding="utf-8") == "x = 1\n"
    finally:
        reset_workspace_scope(tokens)


@pytest.mark.asyncio
async def test_apply_patch_dry_run_does_not_write(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    target = ws / "a.py"
    target.write_text("x = 1\n", encoding="utf-8")
    tokens = workspace_scope(workspace_root=str(ws), workspace_jail_enabled=True)
    try:
        result = await ApplyPatchTool().execute(
            patch=_patch_doc(
                "*** Update File: a.py",
                "@@",
                "-x = 1",
                "+x = 2",
            ),
            dry_run=True,
        )
        payload = json.loads(result)
        assert payload["ok"] is True
        assert payload.get("dry_run") is True
        assert "x = 2" in payload.get("diff", "")
        assert target.read_text(encoding="utf-8") == "x = 1\n"
    finally:
        reset_workspace_scope(tokens)


@pytest.mark.asyncio
async def test_apply_patch_jail_escape_rejected(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("nope\n", encoding="utf-8")
    tokens = workspace_scope(workspace_root=str(ws), workspace_jail_enabled=True)
    try:
        result = await ApplyPatchTool().execute(
            patch=_patch_doc(
                "*** Add File: ../secret.txt",
                "+pwned",
            )
        )
        payload = json.loads(result)
        assert payload["ok"] is False
        assert payload.get("code") in {"jail", "exists"}
        assert secret.read_text(encoding="utf-8") == "nope\n"
    finally:
        reset_workspace_scope(tokens)


def test_alias_edit_and_apply_patch_and_enter_plan_mode():
    assert resolve_tool_name("Edit") == "patch_file"
    assert resolve_tool_name("ApplyPatch") == "apply_patch"
    assert resolve_tool_name("EnterPlanMode") == "plan_mode"
    assert infer_alias_action("EnterPlanMode", "plan_mode", {})["action"] == "enter"


def test_ask_user_accepts_legacy_question_string():
    items, reason = normalize_ask_user_args(question="Use JWT?", context="auth")
    assert items[0]["id"] == "q1"
    assert items[0]["prompt"] == "Use JWT?"
    assert items[0]["allow_free_text"] is True
    assert reason == "auth"


@pytest.mark.asyncio
async def test_ask_user_legacy_execute_with_bridge():
    class Bridge:
        async def ask_user(self, name, question, *, context="", questions=None):
            assert question == "Use JWT?"
            return json.dumps({"q1": ["yes"]})

    tokens = subagent_scope("coder", interaction_bridge=Bridge())
    try:
        raw = await AskUserTool().execute(question="Use JWT?")
        payload = json.loads(raw)
        assert payload["ok"] is True
        assert payload["answers"]["q1"] == ["yes"]
    finally:
        reset_subagent_scope(tokens)


@pytest.mark.asyncio
async def test_notebook_edit_replace_cell(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {"kernelspec": {"name": "python3"}},
        "cells": [
            {
                "id": "c1",
                "cell_type": "code",
                "metadata": {},
                "source": ["print(1)\n"],
                "outputs": [{"output_type": "stream", "text": ["1\n"]}],
                "execution_count": 1,
            }
        ],
    }
    path = ws / "n.ipynb"
    path.write_text(json.dumps(nb), encoding="utf-8")
    tokens = workspace_scope(workspace_root=str(ws), workspace_jail_enabled=True)
    try:
        raw = await NotebookEditTool().execute(
            path="n.ipynb",
            edit_mode="replace",
            cell_id="c1",
            source="print(2)",
        )
        payload = json.loads(raw)
        assert payload["ok"] is True
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert "print(2)" in "".join(loaded["cells"][0]["source"])
        assert loaded["metadata"]["kernelspec"]["name"] == "python3"
    finally:
        reset_workspace_scope(tokens)


@pytest.mark.asyncio
async def test_plan_mode_enter_blocks_write_file(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.py").write_text("keep\n", encoding="utf-8")
    ws_tokens = workspace_scope(workspace_root=str(ws), workspace_jail_enabled=True)
    conv = conversation_scope("plan-mode-test")
    try:
        exit_plan_mode()
        entered = json.loads(await PlanModeTool().execute(action="enter", plan="do x"))
        assert entered["ok"] is True
        assert entered["active"] is True
        reg = ToolRegistry(
            workspace_root=str(ws),
            workspace_jail_enabled=True,
            profile_name="default",
        )
        reg.register_all()
        blocked = await reg.execute(
            _call("write_file", path="a.py", content="mutated\n"),
            conversation_id="plan-mode-test",
        )
        payload = json.loads(blocked)
        assert payload["ok"] is False
        assert payload["code"] == "plan_mode_blocked"
        assert (ws / "a.py").read_text(encoding="utf-8") == "keep\n"
        await PlanModeTool().execute(action="exit", require_approval=False)
    finally:
        exit_plan_mode()
        reset_conversation_scope(conv)
        reset_workspace_scope(ws_tokens)


@pytest.mark.asyncio
async def test_tool_search_finds_builtin_by_description():
    registry = ToolRegistry(profile_name="default")
    registry.register_all()
    token = tools_registry_scope(registry)
    try:
        raw = await ToolSearchTool().execute(query="Codex-style multi-file patch")
        payload = json.loads(raw)
        assert payload["ok"] is True
        names = [m["name"] for m in payload["matches"]]
        assert "apply_patch" in names
    finally:
        reset_tools_registry_scope(token)


@pytest.mark.asyncio
async def test_subagent_control_list_empty_manager():
    raw = await SubagentControlTool().execute(action="list")
    payload = json.loads(raw)
    assert payload["ok"] is True
    assert payload["agents"] == []


@pytest.mark.asyncio
async def test_job_monitor_list_empty_registry():
    prof = profile_scope("coding-agent-tools-empty")
    try:
        raw = await JobMonitorTool().execute(action="list")
        payload = json.loads(raw)
        assert payload["ok"] is True
        assert payload["jobs"] == []
    finally:
        reset_profile_scope(prof)


@pytest.mark.asyncio
async def test_code_mode_apply_patch_gated_by_action_guard(tmp_path):
    from core.tools.code_mode.policy import RUN_CODE_NAME

    ws = tmp_path / "ws"
    ws.mkdir()
    reg = ToolRegistry(
        workspace_root=str(ws),
        workspace_jail_enabled=True,
        profile_name="default",
        tools_presentation="code",
    )
    reg.register_all()
    seen: list[str] = []

    class Guard:
        async def check_and_execute(
            self, tool_name, tool_instance, arguments, execute_fn, conversation_id="default"
        ):
            seen.append(tool_name)
            kwargs = filter_execute_kwargs(execute_fn, arguments)
            return await execute_fn(**kwargs)

    reg.set_action_guard(Guard())
    out = await reg.execute(
        _call(
            RUN_CODE_NAME,
            code=(
                "return tools.apply_patch(patch="
                "'*** Begin Patch\\n*** Add File: n.py\\n+ok\\n*** End Patch\\n')"
            ),
            description="apply patch",
        )
    )
    assert "apply_patch" in seen
    assert (ws / "n.py").read_text(encoding="utf-8") in {"ok\n", "ok"}
    assert "ok" in out or '"ok": true' in out.lower() or "n.py" in out


def test_extract_apply_patch_from_shell_heredoc():
    command = "apply_patch <<'EOF'\n*** Begin Patch\n*** Add File: a.py\n+x\n*** End Patch\nEOF"
    doc = extract_apply_patch_document(command)
    assert doc is not None
    assert "*** Begin Patch" in doc
