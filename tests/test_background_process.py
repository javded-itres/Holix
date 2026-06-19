"""Tests for background project process registry and tools."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from core.presenters.live_buffer import LiveTranscriptBuffer
from core.runtime.background_process import BackgroundProcessRegistry
from core.runtime.background_process_health import ProcessHealthReport
from core.tools.background_process import (
    CheckBackgroundProcessTool,
    ListBackgroundProcessesTool,
    StartBackgroundProcessTool,
    StopBackgroundProcessTool,
    parse_start_tool_result,
)
from core.tools.execution_context import (
    conversation_scope,
    profile_scope,
    reset_conversation_scope,
    reset_profile_scope,
)


@pytest.fixture
def registry() -> BackgroundProcessRegistry:
    return BackgroundProcessRegistry()


@pytest.fixture
def scope_tokens():
    conv = conversation_scope("test-conv")
    prof = profile_scope("test-profile")
    yield
    reset_conversation_scope(conv)
    reset_profile_scope(prof)


def _mock_popen(pid: int = 4242) -> MagicMock:
    popen = MagicMock()
    popen.pid = pid
    return popen


@pytest.mark.asyncio
async def test_registry_start_and_stop(registry: BackgroundProcessRegistry, tmp_path) -> None:
    log_dir = tmp_path / ".holix" / "process-logs"
    popen = _mock_popen(9001)

    with (
        patch("core.runtime.background_process.popen_background", return_value=popen),
        patch("core.runtime.background_process.terminate_process") as terminate,
        patch(
            "core.runtime.background_process.is_process_alive",
            side_effect=[True, False],
        ),
        patch("core.runtime.port_utils.find_busy_ports", return_value=[]),
        patch("core.runtime.port_utils.force_free_ports", return_value=[]),
        patch("core.workspace.get_effective_workspace_root", return_value=tmp_path),
    ):
        record = await registry.start(
            command="sleep 60",
            label="Sleep",
            conversation_id="c1",
            profile="p1",
        )
        stopped = await registry.stop(record.process_id)

    assert record.process_id.startswith("proc_")
    assert record.pid == 9001
    assert record.label == "Sleep"
    assert log_dir.exists()
    assert stopped is not None
    assert stopped.process_id == record.process_id
    terminate.assert_called_once_with(9001, grace=2.0)


@pytest.mark.asyncio
async def test_registry_keeps_other_sessions_alive(registry: BackgroundProcessRegistry, tmp_path) -> None:
    first = _mock_popen(100)
    second = _mock_popen(200)
    third = _mock_popen(300)

    with (
        patch("core.runtime.background_process.popen_background", side_effect=[first, second, third]),
        patch("core.runtime.background_process.terminate_process") as terminate,
        patch("core.runtime.background_process.is_process_alive", return_value=True),
        patch("core.runtime.port_utils.find_busy_ports", return_value=[]),
        patch("core.runtime.port_utils.force_free_ports", return_value=[]),
        patch("core.workspace.get_effective_workspace_root", return_value=tmp_path),
    ):
        rec1 = await registry.start(
            command="uvicorn --port 8000",
            label="backend",
            conversation_id="c1",
            profile="p1",
        )
        rec2 = await registry.start(
            command="uvicorn --port 8001",
            label="frontend",
            conversation_id="c2",
            profile="p1",
        )
        rec3 = await registry.start(
            command="sleep 60",
            label="same-session",
            conversation_id="c1",
            profile="p1",
        )

        assert rec1.process_id != rec2.process_id != rec3.process_id
        active_c1 = registry.active_for_scope(profile="p1", conversation_id="c1")
        active_c2 = registry.active_for_scope(profile="p1", conversation_id="c2")
        assert active_c1 is not None
        assert active_c1.process_id == rec3.process_id
        assert active_c2 is not None
        assert active_c2.process_id == rec2.process_id
        terminate.assert_called_once_with(100, grace=2.0)


@pytest.mark.asyncio
async def test_registry_start_uses_workspace_root_without_cwd(
    registry: BackgroundProcessRegistry,
    tmp_path,
) -> None:
    project = tmp_path / "my-project"
    project.mkdir()
    popen = _mock_popen(9001)
    captured_cwd: list[str] = []

    def capture_spawn(argv, *, stdout, stderr, cwd, env=None):
        captured_cwd.append(cwd)
        return popen

    with (
        patch("core.runtime.background_process.popen_background", side_effect=capture_spawn),
        patch("core.runtime.background_process.terminate_process"),
        patch("core.runtime.background_process.is_process_alive", return_value=True),
        patch("core.runtime.port_utils.find_busy_ports", return_value=[]),
        patch("core.runtime.port_utils.force_free_ports", return_value=[]),
        patch("core.workspace.get_effective_workspace_root", return_value=None),
        patch(
            "core.tools.execution_context.get_workspace_root",
            return_value=str(project),
        ),
        patch(
            "core.tools.execution_context.is_workspace_jail_enabled",
            return_value=False,
        ),
    ):
        record = await registry.start(
            command="npm run dev",
            label="dev",
            conversation_id="c1",
            profile="p1",
        )

    assert captured_cwd == [str(project.resolve())]
    assert record.log_path.startswith(str(project / ".holix" / "process-logs"))


@pytest.mark.asyncio
async def test_registry_replaces_running_process(registry: BackgroundProcessRegistry, tmp_path) -> None:
    first = _mock_popen(100)
    second = _mock_popen(200)

    with (
        patch("core.runtime.background_process.popen_background", side_effect=[first, second]),
        patch("core.runtime.background_process.terminate_process"),
        patch("core.runtime.background_process.is_process_alive", return_value=True),
        patch("core.runtime.port_utils.find_busy_ports", return_value=[]),
        patch("core.runtime.port_utils.force_free_ports", return_value=[]),
        patch("core.workspace.get_effective_workspace_root", return_value=tmp_path),
    ):
        rec1 = await registry.start(
            command="sleep 1",
            label="first",
            conversation_id="c1",
            profile="p1",
        )
        rec2 = await registry.start(
            command="sleep 2",
            label="second",
            conversation_id="c1",
            profile="p1",
        )
        active = registry.active_for_scope(profile="p1", conversation_id="c1")

    assert rec1.process_id != rec2.process_id
    assert active is not None
    assert active.process_id == rec2.process_id


@pytest.mark.asyncio
async def test_start_tool_disabled_without_terminal(scope_tokens) -> None:
    tool = StartBackgroundProcessTool()
    with patch("config.settings.enable_terminal_tool", False):
        result = await tool.execute(command="npm run dev")
    assert "requires terminal tool" in result


@pytest.mark.asyncio
async def test_start_tool_emits_event_and_health(scope_tokens, tmp_path) -> None:
    tool = StartBackgroundProcessTool()
    emitted: list = []
    popen = _mock_popen(5555)
    healthy = ProcessHealthReport(
        process_id="proc_x",
        label="Py",
        pid=5555,
        status="healthy",
        running=True,
    )

    def capture(event):
        emitted.append(event)

    async def fake_check(*args, **kwargs):
        return healthy

    with (
        patch("config.settings.enable_terminal_tool", True),
        patch("core.runtime.background_process.popen_background", return_value=popen),
        patch("core.runtime.background_process.is_process_alive", return_value=True),
        patch("core.runtime.port_utils.find_busy_ports", return_value=[]),
        patch("core.runtime.port_utils.force_free_ports", return_value=[]),
        patch("core.workspace.get_effective_workspace_root", return_value=tmp_path),
        patch("core.tools.execution_context.get_agent_emit", return_value=capture),
        patch(
            "core.tools.background_process._check_and_format",
            side_effect=fake_check,
        ),
    ):
        result = await tool.execute(
            command="sleep 30",
            label="Py",
            startup_wait_seconds=0,
        )

    assert "Background process started" in result
    assert "pid: 5555" in result
    assert "HEALTHY" in result
    assert len(emitted) == 1
    assert emitted[0].pid == 5555
    assert emitted[0].label == "Py"


@pytest.mark.asyncio
async def test_check_tool_reports_error(scope_tokens, tmp_path) -> None:
    registry = BackgroundProcessRegistry()
    bad = ProcessHealthReport(
        process_id="proc_bad",
        label="srv",
        pid=3333,
        status="error_in_log",
        running=True,
        error_snippets=["ModuleNotFoundError: missing"],
        recommendation="fix it",
    )

    with (
        patch("core.runtime.background_process.get_background_process_registry", return_value=registry),
        patch.object(registry, "check_health", return_value=bad),
    ):
        result = await CheckBackgroundProcessTool().execute(wait_seconds=0)

    assert "ERROR_IN_LOG" in result
    assert "ModuleNotFoundError" in result
    assert "restart_background_process" in result


@pytest.mark.asyncio
async def test_stop_for_scope_when_parent_pid_dead(scope_tokens, tmp_path) -> None:
    registry = BackgroundProcessRegistry()
    popen = _mock_popen(8888)

    with (
        patch("core.runtime.background_process.popen_background", return_value=popen),
        patch("core.runtime.background_process.terminate_process"),
        patch("core.runtime.background_process.is_process_alive", return_value=False),
        patch("core.runtime.port_utils.find_busy_ports", return_value=[]),
        patch("core.runtime.port_utils.force_free_ports", return_value=[4242]),
        patch("core.workspace.get_effective_workspace_root", return_value=tmp_path),
    ):
        await registry.start(
            command="uvicorn app:app --port 8000",
            label="api",
            conversation_id="c1",
            profile="p1",
        )
        stopped = await registry.stop_for_scope(profile="p1", conversation_id="c1")

    assert stopped is not None
    assert stopped.label == "api"


@pytest.mark.asyncio
async def test_stop_tool_by_scope(scope_tokens, tmp_path) -> None:
    registry = BackgroundProcessRegistry()
    popen = _mock_popen(7777)

    with (
        patch("core.runtime.background_process.popen_background", return_value=popen),
        patch("core.runtime.background_process.terminate_process"),
        patch("core.runtime.background_process.is_process_alive", return_value=True),
        patch("core.runtime.port_utils.find_busy_ports", return_value=[]),
        patch("core.runtime.port_utils.force_free_ports", return_value=[]),
        patch("core.workspace.get_effective_workspace_root", return_value=tmp_path),
        patch(
            "core.runtime.background_process.get_background_process_registry",
            return_value=registry,
        ),
    ):
        await registry.start(
            command="sleep 1",
            label="srv",
            conversation_id="test-conv",
            profile="test-profile",
        )
        tool = StopBackgroundProcessTool()
        result = await tool.execute()

    assert "Stopped background process" in result
    assert "7777" in result


@pytest.mark.asyncio
async def test_list_tool_empty(scope_tokens) -> None:
    registry = BackgroundProcessRegistry()
    with patch(
        "core.runtime.background_process.get_background_process_registry",
        return_value=registry,
    ):
        result = await ListBackgroundProcessesTool().execute()
    assert result == "No background processes for this session."


@pytest.mark.asyncio
async def test_start_tool_rejects_busy_port(scope_tokens, tmp_path) -> None:
    tool = StartBackgroundProcessTool()
    with (
        patch("config.settings.enable_terminal_tool", True),
        patch("core.runtime.background_process.popen_background") as popen_mock,
        patch("core.runtime.port_utils.find_busy_ports", return_value=[8000]),
        patch("core.runtime.port_utils.force_free_ports", return_value=[]),
        patch("core.workspace.get_effective_workspace_root", return_value=tmp_path),
    ):
        result = await tool.execute(command="uvicorn app:app --port 8000")
    popen_mock.assert_not_called()
    assert "already in use" in result
    assert "8000" in result
    assert "restart_background_process" in result


def test_parse_start_tool_result() -> None:
    body = (
        "Background process started.\n"
        "- id: proc_abc123\n"
        "- label: FastAPI :8000\n"
        "- pid: 4242\n"
        "\n"
        "Background process health: CRASHED\n"
    )
    parsed = parse_start_tool_result(body)
    assert parsed is not None
    assert parsed["process_id"] == "proc_abc123"
    assert parsed["pid"] == 4242
    assert parsed["healthy"] is False
    assert parsed["status"] == "crashed"


def test_live_buffer_renders_background_process() -> None:
    buf = LiveTranscriptBuffer(profile="p1", mode="react")
    buf.set_background_process(label="uvicorn :8000 · pid 1234", process_id="proc_abc")
    text = buf.render_plain()
    assert "🟢 Process: uvicorn :8000 · pid 1234" in text