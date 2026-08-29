"""Ask the human a structured question (main agent or sub-agent)."""

from __future__ import annotations

import json
from typing import Any

from core.tools.base import BaseTool
from core.tools.execution_context import (
    get_interaction_bridge,
    get_subagent_name,
    get_tools_registry,
)
from core.tools.result import tool_err, tool_ok


def normalize_ask_user_args(
    question: str | None = None,
    context: str = "",
    questions: list[dict[str, Any]] | None = None,
    reason: str = "",
    **_: Any,
) -> tuple[list[dict[str, Any]], str]:
    """Accept the new questions[] schema or a legacy question string."""
    items: list[dict[str, Any]] = []
    if isinstance(questions, list) and questions:
        for raw in questions[:5]:
            if not isinstance(raw, dict):
                continue
            qid = str(raw.get("id") or "").strip() or f"q{len(items) + 1}"
            prompt = str(raw.get("prompt") or raw.get("question") or "").strip()
            if not prompt:
                continue
            options = []
            for opt in raw.get("options") or []:
                if not isinstance(opt, dict):
                    continue
                oid = str(opt.get("id") or "").strip()
                label = str(opt.get("label") or "").strip()
                if not oid or not label:
                    continue
                options.append(
                    {
                        "id": oid,
                        "label": label,
                        "description": str(opt.get("description") or ""),
                    }
                )
            options = options[:8]
            items.append(
                {
                    "id": qid,
                    "prompt": prompt,
                    "header": str(raw.get("header") or ""),
                    "allow_free_text": bool(raw.get("allow_free_text", True)),
                    "multi_select": bool(raw.get("multi_select", False)),
                    "options": options,
                }
            )
    if not items:
        prompt = str(question or "").strip()
        if prompt:
            items.append(
                {
                    "id": "q1",
                    "prompt": prompt,
                    "header": "",
                    "allow_free_text": True,
                    "multi_select": False,
                    "options": [],
                }
            )
    reason_text = str(reason or context or "").strip()
    return items[:5], reason_text


def parse_ask_user_reply(
    raw: str,
    questions: list[dict[str, Any]],
) -> dict[str, list[str]]:
    first_id = str(questions[0]["id"]) if questions else "q1"
    text = (raw or "").strip()
    if not text:
        return {first_id: []}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {first_id: [text]}
    if isinstance(payload, dict) and "answers" in payload and isinstance(payload["answers"], dict):
        payload = payload["answers"]
    if isinstance(payload, dict):
        out: dict[str, list[str]] = {}
        for key, value in payload.items():
            if isinstance(value, list):
                out[str(key)] = [str(v) for v in value]
            else:
                out[str(key)] = [str(value)]
        return out or {first_id: [text]}
    if isinstance(payload, list):
        return {first_id: [str(v) for v in payload]}
    return {first_id: [text]}


def _resolve_bridge() -> Any | None:
    bridge = get_interaction_bridge()
    if bridge is not None:
        return bridge
    registry = get_tools_registry()
    host = getattr(registry, "_host_agent", None) if registry is not None else None
    if host is None:
        return None
    return getattr(getattr(host, "subagents", None), "interactions", None)


class AskUserTool(BaseTool):
    """Pause the agent and surface structured questions to the human."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "ask_user"
        self.description = (
            "Ask the human one to five clarifying questions when you cannot "
            "proceed. Prefer concrete option buttons; put background in `reason`. "
            "Ambiguous requirements → ask_user before mutating files. "
            "Write prompts in the user's Holix UI language."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "additionalProperties": False,
            "required": ["questions"],
            "properties": {
                "questions": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 5,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["id", "prompt", "allow_free_text"],
                        "properties": {
                            "id": {"type": "string"},
                            "prompt": {"type": "string"},
                            "header": {"type": "string"},
                            "allow_free_text": {"type": "boolean"},
                            "multi_select": {"type": "boolean"},
                            "options": {
                                "type": "array",
                                "maxItems": 8,
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["id", "label"],
                                    "properties": {
                                        "id": {"type": "string"},
                                        "label": {"type": "string"},
                                        "description": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                },
                "reason": {"type": "string"},
                "question": {
                    "type": "string",
                    "description": "Legacy single-question string (wrapped to questions[0]).",
                },
                "context": {
                    "type": "string",
                    "description": "Legacy background (mapped to reason).",
                },
            },
        }

    async def execute(
        self,
        questions: list[dict[str, Any]] | None = None,
        reason: str = "",
        question: str = "",
        context: str = "",
        **extra: Any,
    ) -> str:
        items, reason_text = normalize_ask_user_args(
            question=question,
            context=context,
            questions=questions,
            reason=reason,
            **extra,
        )
        if not items:
            return tool_err("missing_question", "questions is required")

        bridge = _resolve_bridge()
        if bridge is None:
            return tool_err(
                "no_bridge",
                "ask_user has no UI bridge in this session — ask in the reply instead.",
            )

        name = get_subagent_name() or "main"
        ask = getattr(bridge, "ask_user", None)
        if not callable(ask):
            return tool_err("no_bridge", "interaction bridge cannot ask_user")

        try:
            raw = await ask(
                name,
                items[0]["prompt"],
                context=reason_text or items[0].get("header") or "",
                questions=items,
            )
        except Exception as exc:
            return tool_err("error", str(exc))

        text = str(raw or "")
        if "timed out" in text.lower() or text.strip().endswith("timeout"):
            return tool_err("timeout", "no answer from user")
        if text.startswith("Error:"):
            lowered = text.lower()
            if "timed out" in lowered or "timeout" in lowered:
                return tool_err("timeout", text)
            return tool_err("error", text)

        answers = parse_ask_user_reply(text, items)
        return tool_ok(answers=answers)
