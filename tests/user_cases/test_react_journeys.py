"""P0 react user cases: read / write / terminal (unattended tools)."""

from __future__ import annotations

import pytest

from tests.user_cases.scripted_llm import Final, ToolCall


@pytest.mark.user_case
@pytest.mark.integration
@pytest.mark.asyncio
async def test_uc01_read_file_then_answer(harness):
    """UC-01: user asks about a file → read_file → final summary."""
    harness.workspace.write("README.md", "# Holix\nAgent platform\n")
    harness.script(
        [
            ToolCall("read_file", {"path": "README.md"}),
            Final("This repo is Holix, an agent platform."),
        ]
    )

    result = await harness.run("Read README.md and summarize the project.")

    result.assert_no_error_events()
    result.assert_tools_exactly("read_file")
    result.assert_final_contains("Holix")
    tool_out = result.tool_result_text("read_file")
    assert "Agent platform" in tool_out
    assert "Content of" in tool_out or "Holix" in tool_out


@pytest.mark.user_case
@pytest.mark.integration
@pytest.mark.asyncio
async def test_uc02_write_file_creates_workspace_file(harness):
    """UC-02: write_file creates content under workspace jail."""
    harness.script(
        [
            ToolCall(
                "write_file",
                {"path": "notes/out.txt", "content": "hello-uc-02"},
            ),
            Final("Created notes/out.txt with hello-uc-02."),
        ]
    )

    result = await harness.run("Write hello-uc-02 into notes/out.txt")

    result.assert_no_error_events()
    result.assert_tools_exactly("write_file")
    result.assert_final_contains("out.txt")
    assert harness.workspace.exists("notes/out.txt")
    assert harness.workspace.read("notes/out.txt") == "hello-uc-02"
    assert "Created" in result.tool_result_text(
        "write_file"
    ) or "Updated" in result.tool_result_text("write_file")


@pytest.mark.user_case
@pytest.mark.integration
@pytest.mark.asyncio
async def test_uc03_terminal_allowlisted_echo(harness):
    """UC-03: allowlisted terminal command runs under workspace."""
    harness.script(
        [
            ToolCall("run_terminal_command", {"command": "echo UC_OK"}),
            Final("The command printed UC_OK."),
        ]
    )

    result = await harness.run("Run: echo UC_OK")

    result.assert_no_error_events()
    result.assert_no_confirmation()
    result.assert_tools_exactly("run_terminal_command")
    result.assert_final_contains("UC_OK")
    out = result.tool_result_text("run_terminal_command")
    assert "UC_OK" in out
    assert not out.lower().startswith("error:")


@pytest.mark.user_case
@pytest.mark.integration
@pytest.mark.asyncio
async def test_uc06_multi_step_read_then_write(harness):
    """UC-06: multi-step tool order — read source, write derived file."""
    harness.workspace.write("src/input.txt", "payload-uc06\n")
    harness.script(
        [
            ToolCall("read_file", {"path": "src/input.txt"}),
            ToolCall(
                "write_file",
                {"path": "out/copy.txt", "content": "payload-uc06\n"},
            ),
            Final("Copied payload-uc06 from src/input.txt to out/copy.txt."),
        ]
    )

    result = await harness.run("Read src/input.txt and write the same content to out/copy.txt")

    result.assert_no_error_events()
    result.assert_no_confirmation()
    result.assert_tools_exactly("read_file", "write_file")
    assert "payload-uc06" in result.tool_result_text("read_file")
    assert harness.workspace.exists("out/copy.txt")
    assert harness.workspace.read("out/copy.txt") == "payload-uc06\n"
    result.assert_final_contains("payload-uc06")
