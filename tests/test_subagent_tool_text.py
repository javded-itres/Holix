"""Sub-agent tool text extraction for messenger delivery."""

from __future__ import annotations

import json

from core.presenters.final_content import resolve_messenger_final_content
from core.presenters.subagent_tool_text import (
    extract_subagent_tool_text,
    format_subagent_tool_notice,
    pick_best_tool_final,
)


def test_wait_subagent_result_notice_extracts_response() -> None:
    raw = json.dumps(
        {
            "job_id": "researcher",
            "success": True,
            "response": "Найдено 5 источников по теме SaaS.",
            "error": None,
        },
        ensure_ascii=False,
    )
    notice = format_subagent_tool_notice("wait_subagent_result", raw)
    assert "researcher" in notice
    assert "Найдено 5 источников" in notice
    assert "{" not in notice


def test_pick_best_tool_final_prefers_wait_over_delegate() -> None:
    recent = [
        {
            "name": "delegate_to_subagent",
            "full_result": json.dumps(
                {"status": "spawned", "job_id": "coder", "agent_type": "coder"},
                ensure_ascii=False,
            ),
        },
        {
            "name": "wait_subagent_result",
            "full_result": json.dumps(
                {
                    "job_id": "coder",
                    "success": True,
                    "response": "Код готов и протестирован.",
                },
                ensure_ascii=False,
            ),
        },
    ]
    text = pick_best_tool_final(recent)
    assert "Код готов" in text
    assert "spawned" not in text


def test_resolve_final_uses_wait_subagent_json() -> None:
    recent = [
        {
            "name": "wait_subagent_result",
            "full_result": json.dumps(
                {
                    "job_id": "writer",
                    "success": True,
                    "response": "Черновик документа готов.",
                },
                ensure_ascii=False,
            ),
        }
    ]
    text = resolve_messenger_final_content(
        "No response generated",
        recent_tool_results=recent,
    )
    assert "Черновик документа готов" in text


def test_pick_best_formats_studio_projects_json() -> None:
    recent = [
        {
            "tool_name": "mcp_holix_studio_projects_list_tool",
            "result": json.dumps(
                {
                    "ok": True,
                    "projects": [],
                    "sdd_projects": [
                        {
                            "path": "projects/shop_api",
                            "label": "shop_api",
                            "kind": "sdd",
                            "initialized": True,
                        }
                    ],
                },
                ensure_ascii=False,
            ),
        }
    ]
    text = pick_best_tool_final(recent)
    assert "shop_api" in text
    assert "SDD-проекты" in text
    assert "{" not in text


def test_pick_best_prefers_share_url_over_error() -> None:
    recent = [
        {
            "name": "mcp_holix_studio_documents_upload_file_tool",
            "full_result": json.dumps(
                {"ok": False, "error": "Connection not found"},
                ensure_ascii=False,
            ),
        },
        {
            "name": "mcp_holix_studio_documents_share_tool",
            "full_result": json.dumps(
                {
                    "ok": True,
                    "share": {
                        "name": "КП.docx",
                        "public_url": "https://yadi.sk/i/abc",
                    },
                },
                ensure_ascii=False,
            ),
        },
    ]
    text = pick_best_tool_final(recent)
    assert "https://yadi.sk/i/abc" in text
    assert "КП.docx" in text
    assert "Connection not found" not in text


def test_delegate_spawn_notice_is_human_readable() -> None:
    raw = json.dumps(
        {"status": "spawned", "job_id": "analyst-2", "agent_type": "analyst"},
        ensure_ascii=False,
    )
    notice = format_subagent_tool_notice("delegate_to_subagent", raw)
    assert "analyst-2" in notice
    assert extract_subagent_tool_text("delegate_to_subagent", raw) == ""
