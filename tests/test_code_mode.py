"""Code mode: SDK presentation, isolated worker, inner tools via registry."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from core.subagents.react_agent import FilteredToolRegistry
from core.tools.code_mode.policy import RUN_CODE_NAME, is_forbidden_in_program
from core.tools.code_mode.sdk import build_code_mode_prompt_section, end_tool_schemas
from core.tools.registry import ToolRegistry


def _call(name: str, **kwargs):
    return SimpleNamespace(
        id="c1",
        type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(kwargs, ensure_ascii=False)),
    )


def _registry(tmp_path, *, presentation: str = "code", jail: bool = True) -> ToolRegistry:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "hello.txt").write_text("hello-workspace", encoding="utf-8")
    reg = ToolRegistry(
        workspace_root=str(ws),
        workspace_jail_enabled=jail,
        profile_name="default",
        tools_presentation=presentation,
    )
    reg.register_all()
    return reg


def test_sdk_omits_run_code_and_sorts() -> None:
    schemas = [
        {"function": {"name": "grep", "description": "g", "parameters": {"properties": {}}}},
        {"function": {"name": RUN_CODE_NAME, "description": "x", "parameters": {"properties": {}}}},
        {"function": {"name": "read_file", "description": "r", "parameters": {"properties": {}}}},
        {
            "function": {
                "name": "execute_python",
                "description": "p",
                "parameters": {"properties": {}},
            }
        },
    ]
    names = [s["function"]["name"] for s in end_tool_schemas(schemas)]
    assert names == ["grep", "read_file"]
    text = build_code_mode_prompt_section(schemas)
    available = text.split("The available tools:")[-1]
    assert "**run_code**" not in available
    assert "**read_file**" in available
    assert "**grep**" in available
    assert "execute_python" not in available


def test_native_schemas_hide_run_code(tmp_path) -> None:
    reg = _registry(tmp_path, presentation="native")
    names = [s["function"]["name"] for s in reg.get_schemas()]
    assert RUN_CODE_NAME not in names
    assert "read_file" in names


def test_code_schemas_only_run_code(tmp_path) -> None:
    reg = _registry(tmp_path, presentation="code")
    names = [s["function"]["name"] for s in reg.get_schemas()]
    assert names == [RUN_CODE_NAME]


def test_presentation_by_slot(tmp_path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    reg = ToolRegistry(
        workspace_root=str(ws),
        workspace_jail_enabled=True,
        profile_name="default",
        tools_presentation="native",
        tools_presentation_by_slot={"coder": "code"},
    )
    reg.register_all()
    main = [s["function"]["name"] for s in reg.get_schemas(for_agent_slot="main")]
    coder = [s["function"]["name"] for s in reg.get_schemas(for_agent_slot="coder")]
    assert RUN_CODE_NAME not in main
    assert "read_file" in main
    assert coder == [RUN_CODE_NAME]


@pytest.mark.asyncio
async def test_slot_code_rejects_direct_native(tmp_path) -> None:
    from core.tools.execution_context import agent_slot_scope, reset_agent_slot_scope

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "hello.txt").write_text("hello-workspace", encoding="utf-8")
    reg = ToolRegistry(
        workspace_root=str(ws),
        workspace_jail_enabled=True,
        profile_name="default",
        tools_presentation="native",
        tools_presentation_by_slot={"coder": "code"},
    )
    reg.register_all()
    token = agent_slot_scope("coder")
    try:
        out = await reg.execute(_call("read_file", path="hello.txt"))
    finally:
        reset_agent_slot_scope(token)
    assert "only `run_code`" in out
    assert "hello-workspace" not in out


@pytest.mark.asyncio
async def test_code_mode_rejects_direct_native_tool(tmp_path) -> None:
    reg = _registry(tmp_path, presentation="code")
    out = await reg.execute(_call("read_file", path="hello.txt"))
    assert "only `run_code`" in out
    assert "hello-workspace" not in out


def test_indent_preserves_multiline_string() -> None:
    from core.tools.code_mode.worker import _indent_as_function_body, _run_user

    src = 's = """fastapi==1\nuvicorn==2\n"""\nreturn s\n'
    body = _indent_as_function_body(src)
    assert '    s = """fastapi==1\n' in body
    assert "\nuvicorn==2\n" in body
    assert "    uvicorn" not in body
    value = _run_user(src, {"__builtins__": __builtins__})
    assert value == "fastapi==1\nuvicorn==2\n"


def test_background_process_allowed_in_program() -> None:
    assert not is_forbidden_in_program("start_background_process")
    assert not is_forbidden_in_program("check_background_process")
    assert not is_forbidden_in_program("stop_background_process")
    assert not is_forbidden_in_program("restart_background_process")
    assert is_forbidden_in_program("execute_python")
    assert is_forbidden_in_program("ask_user")


@pytest.mark.asyncio
async def test_write_file_preserves_multiline_content(tmp_path) -> None:
    reg = _registry(tmp_path, presentation="code")
    out = await reg.execute(
        _call(
            RUN_CODE_NAME,
            code=(
                'tools.write_file(path=\'req.txt\', content="""fastapi==1\n'
                "uvicorn==2\n"
                '""")\n'
                "return tools.read_file(path='req.txt')"
            ),
            description="write req",
        )
    )
    text = (tmp_path / "ws" / "req.txt").read_text(encoding="utf-8")
    assert text == "fastapi==1\nuvicorn==2\n"
    assert "fastapi==1" in out


@pytest.mark.asyncio
async def test_run_code_terminal_pwd_is_workspace(tmp_path) -> None:
    reg = _registry(tmp_path, presentation="code", jail=False)
    out = await reg.execute(
        _call(
            RUN_CODE_NAME,
            code='return tools.run_terminal_command(command="pwd")',
            description="pwd",
        )
    )
    ws = str((tmp_path / "ws").resolve())
    assert ws in out.replace("/private", "") or ws in out


@pytest.mark.asyncio
async def test_run_code_reads_workspace_file(tmp_path) -> None:
    reg = _registry(tmp_path, presentation="code")
    out = await reg.execute(
        _call(
            RUN_CODE_NAME,
            code='return tools.read_file(path="hello.txt")',
            description="read hello",
        )
    )
    assert "hello-workspace" in out
    assert "Error:" not in out.split("hello-workspace")[0] or "hello-workspace" in out


@pytest.mark.asyncio
async def test_run_code_jail_blocks_escape(tmp_path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("nope", encoding="utf-8")
    reg = _registry(tmp_path, presentation="code", jail=True)
    out = await reg.execute(
        _call(
            RUN_CODE_NAME,
            code='return tools.read_file(path="../secret.txt")',
            description="escape",
        )
    )
    assert "nope" not in out
    assert "Error" in out or "outside" in out.lower() or "jail" in out.lower()


@pytest.mark.asyncio
async def test_run_code_forbids_execute_python(tmp_path) -> None:
    reg = _registry(tmp_path, presentation="code")
    out = await reg.execute(
        _call(
            RUN_CODE_NAME,
            code='return tools.execute_python(code="1+1")',
            description="escape python",
        )
    )
    assert "cannot be called" in out or "ToolCallError" in out or "Error" in out
    assert "RESULT:" not in out


@pytest.mark.asyncio
async def test_run_code_forbids_nested_run_code(tmp_path) -> None:
    assert is_forbidden_in_program(RUN_CODE_NAME)
    reg = _registry(tmp_path, presentation="code")
    out = await reg.execute(
        _call(
            RUN_CODE_NAME,
            code='return tools.run_code(code="return 1", description="nested")',
            description="nest",
        )
    )
    assert "cannot be called" in out or "Error" in out


@pytest.mark.asyncio
async def test_import_tools_aliases_sdk(tmp_path) -> None:
    reg = _registry(tmp_path, presentation="code")
    out = await reg.execute(
        _call(
            RUN_CODE_NAME,
            code='import tools\nreturn tools.read_file(path="hello.txt")',
            description="import tools",
        )
    )
    assert "hello-workspace" in out
    assert "ImportError" not in out


@pytest.mark.asyncio
async def test_from_tools_import_aliases_sdk(tmp_path) -> None:
    reg = _registry(tmp_path, presentation="code")
    out = await reg.execute(
        _call(
            RUN_CODE_NAME,
            code='from tools import read_file\nreturn read_file(path="hello.txt")',
            description="from tools import",
        )
    )
    assert "hello-workspace" in out
    assert "ImportError" not in out


@pytest.mark.asyncio
async def test_worker_cannot_import_os(tmp_path) -> None:
    reg = _registry(tmp_path, presentation="code")
    out = await reg.execute(
        _call(
            RUN_CODE_NAME,
            code="import os\nreturn os.listdir('/')",
            description="os import",
        )
    )
    assert "not allowed" in out.lower() or "ImportError" in out or "Error" in out
    assert "run_terminal_command" in out.lower() or "list_directory" in out.lower()
    assert "site-packages" not in out
    assert "worker.py" not in out


@pytest.mark.asyncio
async def test_worker_user_exception_has_no_traceback_dump(tmp_path) -> None:
    reg = _registry(tmp_path, presentation="code")
    out = await reg.execute(
        _call(
            RUN_CODE_NAME,
            code='print("keep-me")\nraise IndexError("boom")',
            description="user crash",
        )
    )
    assert "keep-me" in out
    assert "IndexError: boom" in out
    assert "run_code line" in out
    assert "Traceback" not in out
    assert "worker.py" not in out
    assert "site-packages" not in out


@pytest.mark.asyncio
async def test_native_tool_in_code_mode_explains_wrap(tmp_path) -> None:
    reg = _registry(tmp_path, presentation="code")
    out = await reg.execute(_call("list_directory", path="."))
    assert "run_code" in out
    assert "tools.list_directory" in out


@pytest.mark.asyncio
async def test_run_code_timeout_kills_worker(tmp_path) -> None:
    reg = _registry(tmp_path, presentation="code")
    out = await reg.execute(
        _call(
            RUN_CODE_NAME,
            code="while True:\n    pass",
            description="hang",
            timeout=1,
        )
    )
    assert "timeout" in out.lower() or "timed out" in out.lower() or "failed" in out.lower()


@pytest.mark.asyncio
async def test_inner_result_truncated(tmp_path) -> None:
    reg = _registry(tmp_path, presentation="code")
    huge = tmp_path / "ws" / "huge.txt"
    huge.write_text("X" * 50_000, encoding="utf-8")
    out = await reg.execute(
        _call(
            RUN_CODE_NAME,
            code='return tools.read_file(path="huge.txt")',
            description="huge",
        )
    )
    assert "truncated" in out.lower() or len(out) < 40_000


@pytest.mark.asyncio
async def test_filtered_registry_blocks_write_from_program(tmp_path) -> None:
    inner = _registry(tmp_path, presentation="code")
    filt = FilteredToolRegistry(
        inner,
        allowed={"read_file", "list_directory", "grep"},
        inherit_mcp=False,
        mcp_servers=[],
    )
    out = await filt.execute(
        _call(
            RUN_CODE_NAME,
            code='return tools.write_file(path="pwn.txt", content="x")',
            description="write",
        )
    )
    assert not (tmp_path / "ws" / "pwn.txt").exists()
    assert "not available" in out.lower() or "cannot be called" in out.lower() or "Error" in out


@pytest.mark.asyncio
async def test_parallel_readonly_reads_two_files(tmp_path) -> None:
    reg = _registry(tmp_path, presentation="code")
    (tmp_path / "ws" / "b.txt").write_text("second-file", encoding="utf-8")
    out = await reg.execute(
        _call(
            RUN_CODE_NAME,
            code=(
                "return tools.parallel("
                '("read_file", {"path": "hello.txt"}), '
                '("read_file", {"path": "b.txt"})'
                ")"
            ),
            description="batch read",
        )
    )
    assert "hello-workspace" in out
    assert "second-file" in out
    assert "ImportError" not in out


@pytest.mark.asyncio
async def test_parallel_rejects_write(tmp_path) -> None:
    reg = _registry(tmp_path, presentation="code")
    out = await reg.execute(
        _call(
            RUN_CODE_NAME,
            code='return tools.parallel(("write_file", {"path": "x.txt", "content": "n"}))',
            description="batch write",
        )
    )
    assert not (tmp_path / "ws" / "x.txt").exists()
    assert "read-only" in out.lower() or "Error" in out
