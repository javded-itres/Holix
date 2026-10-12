"""Same-agent background tasks: start, track, and wake on completion."""

from __future__ import annotations

import asyncio
import json
import sys

import pytest
from core.runtime.agent_tasks import (
    AgentBackgroundTask,
    format_agent_task_wakeup,
    get_agent_task_registry,
    register_agent_task_listener,
    started_task_message,
    unregister_agent_task_listener,
)
from core.tools.terminal import TerminalTool


@pytest.fixture(autouse=True)
def _clear_tasks():
    registry = get_agent_task_registry()
    registry.clear()
    yield
    registry.clear()


def _spawn_kw() -> dict:
    kw: dict = {}
    if sys.platform != "win32":
        kw["start_new_session"] = True
    return kw


async def _wait_done(task_id: str, timeout: float = 5.0):
    registry = get_agent_task_registry()
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        task = registry.get(task_id)
        if task is not None and not task.is_running():
            return task
        await asyncio.sleep(0.02)
    raise AssertionError(f"task {task_id} did not finish")


@pytest.mark.asyncio
async def test_background_task_wakes_listener_with_output() -> None:
    seen: list[str] = []

    def _on_task(task) -> None:
        seen.append(task.task_id)

    register_agent_task_listener(_on_task)
    try:
        launched = await get_agent_task_registry().launch_shell(
            command="python3 -c \"print('done-marker')\"",
            description="print marker",
            profile="alice",
            conversation_id="conv-1",
            cwd=None,
            use_shell=False,
            argv=[sys.executable, "-c", "print('done-marker')"],
            spawn_kw=_spawn_kw(),
        )
        assert not isinstance(launched, str)
        assert launched.is_running()
        assert "id=" in started_task_message(launched)
        finished = await _wait_done(launched.task_id)
    finally:
        unregister_agent_task_listener(_on_task)

    assert finished.status == "completed"
    assert finished.exit_code == 0
    assert "done-marker" in finished.output
    assert seen == [finished.task_id]
    text = format_agent_task_wakeup(finished)
    assert "Tell the user the result" in text
    assert "Do not paste this note" not in text
    assert "done-marker" in text
    assert get_agent_task_registry().running_count(profile="alice", conversation_id="conv-1") == 0


def test_delivered_media_wakeup_hides_generation_details() -> None:
    task = AgentBackgroundTask(
        task_id="task_img",
        description="image: a door",
        command="a very long prompt",
        profile="admin",
        conversation_id="tg",
        status="completed",
        exit_code=0,
        output=(
            "Saved image: /tmp/pic.png\n"
            "Delivered to the chat. A details button under the file shows the model."
        ),
    )
    text = format_agent_task_wakeup(task)
    assert "details button" in text
    assert "a very long prompt" not in text
    assert "start_background_process" not in text


def test_install_wakeup_does_not_treat_the_note_as_the_bot() -> None:
    task = AgentBackgroundTask(
        task_id="task_pip",
        description="install publisher deps",
        command="cd telegram_channel_publisher && .venv/bin/pip install -r requirements.txt",
        profile="admin",
        conversation_id="tg",
        status="completed",
        exit_code=0,
        output="Successfully installed",
    )
    text = format_agent_task_wakeup(task)
    assert "Tell the user the result" in text
    assert "Successfully installed" in text
    assert "Do not paste this note" not in text
    assert "start_background_process" not in text
    note = started_task_message(task)
    assert note.startswith("Background task started:")
    assert "Do not paste this note" not in note
    assert "not a sub-agent" not in note


@pytest.mark.asyncio
async def test_duplicate_image_calls_in_one_step_collapse() -> None:
    from core.runtime.agent_tasks import collapse_repeat_media_calls, get_agent_task_registry

    call = {
        "id": "1",
        "function": {
            "name": "generate_image",
            "arguments": json.dumps({"prompt": "a pink elephant"}),
        },
    }
    copies = [{**call, "id": str(i)} for i in range(5)]
    kept, stop = collapse_repeat_media_calls(
        copies, profile="default", conversation_id="conv-media"
    )
    assert stop is None
    assert len(kept) == 1

    registry = get_agent_task_registry()

    async def _done() -> str:
        return "Saved image: /tmp/a.png"

    launched = await registry.launch_async(
        description="image",
        command="a pink elephant",
        profile="default",
        conversation_id="conv-media",
        runner=_done,
    )
    assert not isinstance(launched, str)
    assert launched._async_job is not None
    await launched._async_job
    _kept, stop = collapse_repeat_media_calls(
        copies, profile="default", conversation_id="conv-media"
    )
    assert _kept == []
    assert stop is not None
    assert "task_" in stop
    assert "Saved image: /tmp/a.png" in stop


@pytest.mark.asyncio
async def test_background_task_streams_output_before_exit() -> None:
    launched = await get_agent_task_registry().launch_shell(
        command="stream marker",
        description="stream marker",
        profile="alice",
        conversation_id="conv-stream",
        cwd=None,
        use_shell=False,
        argv=[
            sys.executable,
            "-c",
            "import time; print('line-one', flush=True); time.sleep(0.6); print('line-two', flush=True)",
        ],
        spawn_kw=_spawn_kw(),
    )
    assert not isinstance(launched, str)
    deadline = asyncio.get_event_loop().time() + 3
    while asyncio.get_event_loop().time() < deadline:
        if "line-one" in (launched.output or "") and launched.is_running():
            break
        await asyncio.sleep(0.02)
    else:
        raise AssertionError(f"no live output, status={launched.status!r} out={launched.output!r}")
    finished = await _wait_done(launched.task_id)
    assert "line-two" in finished.output
    rows = get_agent_task_registry().snapshot(profile="alice", conversation_id="conv-stream")
    assert rows and rows[0]["task_id"] == finished.task_id
    assert "line-two" in rows[0]["output"]


def test_one_media_start_blocks_a_later_revision_call() -> None:
    from core.runtime.agent_tasks import media_generation_already_started

    messages = [
        {"role": "user", "content": "нарисуй слона"},
        {
            "role": "tool",
            "content": "Background task started: id=task_abc — image: elephant",
        },
        {"role": "user", "content": "## Reflexion (iteration 1)\nImprove the image."},
    ]
    assert media_generation_already_started(messages) is True
    fresh = [{"role": "user", "content": "поправь: добавь человека"}]
    assert media_generation_already_started(fresh) is False
    delivered = [
        {"role": "user", "content": "нарисуй слона"},
        {
            "role": "tool",
            "content": "Background task started: id=task_abc — image: elephant",
        },
        {
            "role": "user",
            "content": "Background task `image` (id=task_abc) finished successfully.",
        },
    ]
    assert media_generation_already_started(delivered) is False


def test_wakeup_turn_is_not_replaced_by_the_idle_list_stop() -> None:
    from core.runtime.agent_tasks import stop_idle_task_lookup, visible_background_final

    state = {
        "messages": [
            {
                "role": "user",
                "content": (
                    "Background task `pytest` (id=task_new) finished successfully. "
                    "Tell the user the result in your own words.\n\n"
                    "Command: uv run pytest -q\n\n"
                    "Output:\n2 passed"
                ),
            }
        ],
        "tool_results": [
            {
                "tool_name": "list_agent_tasks",
                "result": (
                    "Background tasks (same agent, not sub-agents):\n"
                    "- task_old completed exit=0 (4s) — older run"
                ),
            }
        ],
    }
    calls = [{"function": {"name": "list_agent_tasks", "arguments": "{}"}}]
    assert stop_idle_task_lookup(state, calls) is None
    assert visible_background_final("", state["messages"]) == (
        "Background task `pytest` (id=task_new) finished successfully.\n\n2 passed"
    )
    hidden = visible_background_final(
        "Background task started: id=task_new — pytest. Running in this chat.",
        [{"role": "user", "content": "прогони тесты"}],
    )
    assert hidden == ""
    idle = "Фоновых задач нет. Повторно их искать не нужно."
    assert visible_background_final(idle, state["messages"]).startswith("Background task `pytest`")


def test_second_task_list_stops_when_nothing_is_running() -> None:
    from core.runtime.agent_tasks import stop_idle_task_lookup

    state = {
        "tool_results": [
            {
                "tool_name": "list_agent_tasks",
                "result": (
                    "Background tasks (same agent, not sub-agents):\n"
                    "- task_a9eba40f completed exit=0 (5s) — image: a cat"
                ),
            }
        ]
    }
    calls = [{"function": {"name": "list_agent_tasks", "arguments": "{}"}}]
    text = stop_idle_task_lookup(state, calls)
    assert text is not None
    assert "Повторно" in text
    running = {
        "tool_results": [
            {
                "tool_name": "list_agent_tasks",
                "result": "- task_a9eba40f running 3s — image: a cat",
            }
        ]
    }
    assert stop_idle_task_lookup(running, calls) is None


@pytest.mark.asyncio
async def test_start_listener_sees_a_running_task() -> None:
    from core.runtime.agent_tasks import (
        register_agent_task_start_listener,
        unregister_agent_task_start_listener,
    )

    seen: list[str] = []

    def _on_start(task) -> None:
        seen.append(task.task_id)

    register_agent_task_start_listener(_on_start)
    try:
        launched = await get_agent_task_registry().launch_async(
            description="video clip",
            profile="alice",
            conversation_id="conv-pin",
            runner=_hang_once,
        )
    finally:
        unregister_agent_task_start_listener(_on_start)
    assert not isinstance(launched, str)
    assert seen == [launched.task_id]
    await get_agent_task_registry().stop(launched.task_id)
    await _wait_done(launched.task_id)


async def _hang_once() -> str:
    await asyncio.Event().wait()
    return "never"


@pytest.mark.asyncio
async def test_async_background_task_has_no_timeout_and_can_be_stopped() -> None:
    async def _hang() -> str:
        await asyncio.Event().wait()
        return "never"

    launched = await get_agent_task_registry().launch_async(
        description="hang",
        profile="alice",
        conversation_id="conv-async",
        runner=_hang,
    )
    assert not isinstance(launched, str)
    assert launched.is_running()
    message = await get_agent_task_registry().stop(launched.task_id)
    assert launched.task_id in message
    finished = await _wait_done(launched.task_id)
    assert finished.status == "killed"


@pytest.mark.asyncio
async def test_stop_agent_task() -> None:
    launched = await get_agent_task_registry().launch_shell(
        command="sleep 30",
        description="sleep",
        profile="alice",
        conversation_id="conv-2",
        cwd=None,
        use_shell=False,
        argv=["sleep", "30"],
        spawn_kw=_spawn_kw(),
    )
    assert not isinstance(launched, str)
    message = await get_agent_task_registry().stop(launched.task_id)
    assert launched.task_id in message
    finished = await _wait_done(launched.task_id)
    assert finished.status == "killed"


@pytest.mark.asyncio
async def test_terminal_tool_background_returns_immediately(monkeypatch) -> None:
    from core.tools import terminal as terminal_mod

    from config import settings

    monkeypatch.setattr(settings, "enable_terminal_tool", True)
    monkeypatch.setattr(terminal_mod.settings, "enable_terminal_tool", True)
    monkeypatch.setattr(terminal_mod, "terminal_whitelist_enabled", lambda: False)
    tool = TerminalTool()
    result = await tool.execute(
        command=f"{sys.executable} -c \"import time; time.sleep(0.4); print('later')\"",
        background=True,
        description="slow print",
        timeout=1,
    )
    assert result.startswith("Background task started:")
    task_id = result.split("id=", 1)[1].split(" ", 1)[0]
    listing = get_agent_task_registry().format_list(profile="default", conversation_id="default")
    assert task_id in listing
    finished = await _wait_done(task_id)
    assert "later" in finished.output
    assert finished.status == "completed"
    get_agent_task_registry().clear()
    listing = get_agent_task_registry().format_list(profile="default", conversation_id="default")
    assert task_id in listing
    assert "completed" in listing
