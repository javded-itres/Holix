"""Execute A2A messages against a Holix agent instance."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from core.a2a.models import (
    A2AArtifact,
    A2AMessage,
    A2APart,
    A2ATask,
    A2ATaskStatus,
    TaskState,
    new_id,
)
from core.a2a.store import A2ATaskStore, get_a2a_task_store

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _history_len(cfg: dict[str, Any]) -> int | None:
    history_length = cfg.get("historyLength")
    try:
        return int(history_length) if history_length is not None else None
    except (TypeError, ValueError):
        return None


def _prepare_task(
    *,
    message: A2AMessage | dict[str, Any],
    profile: str,
    store: A2ATaskStore | None,
) -> tuple[A2AMessage, A2ATask, A2ATaskStore, str, str]:
    msg = A2AMessage.parse(message) if not isinstance(message, A2AMessage) else message
    text = msg.text_content()
    if not text:
        raise ValueError("message must include at least one text part")

    task_store = store or get_a2a_task_store()
    context_id = (msg.contextId or "").strip() or new_id("ctx_")
    task_id = (msg.taskId or "").strip() or new_id("task_")
    conversation_id = f"a2a:{context_id}"

    existing = task_store.get(task_id)
    if existing is not None:
        task = existing
        task.history.append(msg)
    else:
        task = A2ATask(
            id=task_id,
            contextId=context_id,
            status=A2ATaskStatus(state=TaskState.WORKING, timestamp=_now()),
            history=[msg],
            profile=profile,
            conversation_id=conversation_id,
        )
        task_store.put(task)

    task.status = A2ATaskStatus(state=TaskState.WORKING, timestamp=_now())
    task.conversation_id = conversation_id
    task_store.put(task)
    return msg, task, task_store, text, conversation_id


def _complete_task(
    task: A2ATask,
    task_store: A2ATaskStore,
    *,
    answer: str,
    failed: bool = False,
) -> None:
    context_id = task.contextId
    task_id = task.id
    agent_msg = A2AMessage.from_agent_text(
        answer, context_id=context_id, task_id=task_id
    )
    task.history.append(agent_msg)
    task.artifacts = [
        A2AArtifact(
            name="response",
            description="Agent reply",
            parts=[A2APart(kind="text", text=answer)],
        )
    ]
    task.status = A2ATaskStatus(
        state=TaskState.FAILED if failed else TaskState.COMPLETED,
        message=agent_msg,
        timestamp=_now(),
    )
    task_store.put(task)


def _status_update(
    task: A2ATask,
    state: TaskState,
    *,
    message: A2AMessage | None = None,
    final: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "taskId": task.id,
        "contextId": task.contextId,
        "status": {
            "state": state.value,
            "timestamp": _now(),
        },
        "final": final,
    }
    if message is not None:
        payload["status"]["message"] = message.model_dump(exclude_none=True)
    return {"statusUpdate": payload}


def _artifact_update(
    task: A2ATask,
    *,
    text: str,
    append: bool = True,
    last_chunk: bool = False,
    name: str = "response",
) -> dict[str, Any]:
    art_id = f"art_{task.id}"
    return {
        "artifactUpdate": {
            "taskId": task.id,
            "contextId": task.contextId,
            "artifact": {
                "artifactId": art_id,
                "name": name,
                "parts": [{"kind": "text", "text": text}],
            },
            "append": append,
            "lastChunk": last_chunk,
        }
    }


async def handle_message_send(
    *,
    agent: Any,
    message: A2AMessage | dict[str, Any],
    profile: str = "default",
    configuration: dict[str, Any] | None = None,
    store: A2ATaskStore | None = None,
) -> dict[str, Any]:
    """Process an A2A message and return a Task (blocking by default).

    Maps A2A contextId → Holix conversation_id for multi-turn continuity.
    """
    cfg = configuration if isinstance(configuration, dict) else {}
    _msg, task, task_store, text, conversation_id = _prepare_task(
        message=message, profile=profile, store=store
    )

    try:
        result = await agent.run(
            user_input=text,
            conversation_id=conversation_id,
        )
        answer = (result if isinstance(result, str) else str(result or "")).strip()
        if not answer:
            answer = "(empty response)"
        _complete_task(task, task_store, answer=answer, failed=False)
    except Exception as exc:
        logger.exception("A2A message/send failed profile=%s task=%s", profile, task.id)
        _complete_task(task, task_store, answer=f"Error: {exc}", failed=True)

    return task.to_public_dict(history_length=_history_len(cfg))


async def handle_message_stream(
    *,
    agent: Any,
    message: A2AMessage | dict[str, Any],
    profile: str = "default",
    configuration: dict[str, Any] | None = None,
    store: A2ATaskStore | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield A2A StreamResponse objects while running Holix with stream=True.

    Sequence:
    1. ``{"task": ...}`` — working task snapshot
    2. zero+ ``{"statusUpdate": ...}`` / ``{"artifactUpdate": ...}`` for progress
    3. final ``{"statusUpdate": ..., "final": true}`` and/or completed task fields
    """
    cfg = configuration if isinstance(configuration, dict) else {}
    _msg, task, task_store, text, conversation_id = _prepare_task(
        message=message, profile=profile, store=store
    )
    hist_n = _history_len(cfg)

    # 1) Initial task event
    yield {"task": task.to_public_dict(history_length=hist_n)}

    answer_parts: list[str] = []
    final_text = ""
    last_tool = ""

    try:
        from core.agent_events import (
            AssistantDeltaEvent,
            ErrorEvent,
            FinalResponseEvent,
            ThinkingEvent,
            ToolCallResultEvent,
            ToolCallStartEvent,
        )
        from core.runtime.executor import run_holix

        # Ensure agent ready
        if not getattr(agent, "_initialized", True):
            await agent.initialize()

        async for event in run_holix(
            agent,
            text,
            conversation_id,
            stream=True,
        ):
            # Fan-out to agent bus when present (metrics / studio)
            emit = getattr(agent, "emit", None)
            if callable(emit):
                try:
                    emit(event)
                except Exception:
                    pass

            if isinstance(event, ThinkingEvent):
                note = (getattr(event, "message", None) or "thinking…")[:240]
                yield _status_update(
                    task,
                    TaskState.WORKING,
                    message=A2AMessage.from_agent_text(
                        note, context_id=task.contextId, task_id=task.id
                    ),
                )
            elif isinstance(event, ToolCallStartEvent):
                last_tool = str(getattr(event, "tool_name", "") or "tool")
                yield _status_update(
                    task,
                    TaskState.WORKING,
                    message=A2AMessage.from_agent_text(
                        f"tool: {last_tool}",
                        context_id=task.contextId,
                        task_id=task.id,
                    ),
                )
            elif isinstance(event, ToolCallResultEvent):
                tool = str(getattr(event, "tool_name", "") or last_tool or "tool")
                yield _status_update(
                    task,
                    TaskState.WORKING,
                    message=A2AMessage.from_agent_text(
                        f"tool done: {tool}",
                        context_id=task.contextId,
                        task_id=task.id,
                    ),
                )
            elif isinstance(event, AssistantDeltaEvent):
                chunk = str(getattr(event, "content", None) or getattr(event, "delta", "") or "")
                if chunk:
                    answer_parts.append(chunk)
                    yield _artifact_update(task, text=chunk, append=True, last_chunk=False)
            elif isinstance(event, FinalResponseEvent):
                final_text = (getattr(event, "content", None) or "").strip()
            elif isinstance(event, ErrorEvent):
                final_text = str(getattr(event, "error", None) or event)
                _complete_task(task, task_store, answer=final_text or "Error", failed=True)
                yield _status_update(
                    task,
                    TaskState.FAILED,
                    message=task.status.message,
                    final=True,
                )
                return

        if not final_text and answer_parts:
            final_text = "".join(answer_parts).strip()
        if not final_text:
            # Fallback non-stream if graph produced no final
            try:
                result = await agent.run(
                    user_input=text,
                    conversation_id=conversation_id,
                )
                final_text = (result if isinstance(result, str) else str(result or "")).strip()
            except Exception:
                final_text = ""
        if not final_text:
            final_text = "(empty response)"

        _complete_task(task, task_store, answer=final_text, failed=False)
        # Final artifact (full text) + status
        yield _artifact_update(
            task, text=final_text, append=False, last_chunk=True
        )
        yield _status_update(
            task,
            TaskState.COMPLETED,
            message=task.status.message,
            final=True,
        )
        # Optional full task snapshot for clients that only watch task objects
        yield {"task": task.to_public_dict(history_length=hist_n)}
    except Exception as exc:
        logger.exception(
            "A2A message/stream failed profile=%s task=%s", profile, task.id
        )
        _complete_task(task, task_store, answer=f"Error: {exc}", failed=True)
        yield _status_update(
            task,
            TaskState.FAILED,
            message=task.status.message,
            final=True,
        )



def get_task_public(
    task_id: str,
    *,
    store: A2ATaskStore | None = None,
    history_length: int | None = None,
    profile: str | None = None,
) -> dict[str, Any] | None:
    task_store = store or get_a2a_task_store()
    task = task_store.get(task_id)
    if task is None:
        return None
    if profile and task.profile != profile:
        return None
    return task.to_public_dict(history_length=history_length)


def cancel_task(
    task_id: str,
    *,
    store: A2ATaskStore | None = None,
    profile: str | None = None,
) -> dict[str, Any] | None:
    task_store = store or get_a2a_task_store()
    task = task_store.get(task_id)
    if task is None:
        return None
    if profile and task.profile != profile:
        return None
    state = task.status.state
    if state in {
        TaskState.COMPLETED,
        TaskState.FAILED,
        TaskState.CANCELED,
        TaskState.REJECTED,
    }:
        return task.to_public_dict()
    task.status = A2ATaskStatus(state=TaskState.CANCELED, timestamp=_now())
    task_store.put(task)
    return task.to_public_dict()
