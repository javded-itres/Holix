"""Streaming tool-call edge cases in react_node."""

from __future__ import annotations

from core.graph.nodes.react_node import _streaming_tool_calls_error


def test_streaming_tool_calls_error_detects_truncated_json() -> None:
    err = _streaming_tool_calls_error(
        {
            0: {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "patch_file",
                    "arguments": '{"path": ".holix/HOLIX.md", "replacements": [{"old_string":',
                },
            }
        }
    )
    assert err is not None
    assert "update_holix_section" in err


def test_streaming_tool_calls_error_accepts_valid_json() -> None:
    err = _streaming_tool_calls_error(
        {
            0: {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "update_holix_section",
                    "arguments": (
                        '{"heading": "## Overview", "content": "- Purpose: demo"}'
                    ),
                },
            }
        }
    )
    assert err is None