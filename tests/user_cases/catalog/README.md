# User-case catalog

Product journeys for Holix: **scripted LLM** + **real tools** + isolated workspace.

## How to add a case

1. Prefer a Python test under `tests/user_cases/test_*.py` (see `test_react_journeys.py`).
2. Use the `harness` fixture:

```python
@pytest.mark.user_case
async def test_uc_xx(harness):
    harness.workspace.write("file.txt", "...")
    harness.script([
        ToolCall("read_file", {"path": "file.txt"}),
        Final("Summary..."),
    ])
    result = await harness.run("User message")
    result.assert_tools_exactly("read_file")
    result.assert_final_contains("...")
```

3. Defaults: `auto_allow_threshold=high`, meta/reflexion/subagents/MCP off, workspace jail on.
4. Run: `uv run python -m pytest tests/user_cases -q` or `-m user_case`.

## P0 IDs

| ID | Status | Description |
|----|--------|-------------|
| UC-01 | implemented | read_file → answer |
| UC-02 | implemented | write_file → file exists |
| UC-03 | implemented | run_terminal_command echo (auto-allow) |
| UC-04 | implemented | high-risk terminal + confirm allow |
| UC-05 | implemented | high-risk terminal + deny |
| UC-06 | implemented | multi-step read + write |
| UC-10 | implemented | plan_and_execute write+verify |
| UC-11 | implemented | hybrid write+verify |
| UC-12 | implemented | context compress during run |
| UC-13 | implemented | multi-turn conversation memory |
| UC-14 | implemented | max_steps budget stop |
| UC-20 | implemented | gateway chat completions + real agent |
| UC-21 | implemented | slash /mode + /status |
| UC-22 | implemented | Telegram confirm allow/deny |
| UC-23 | implemented | two profiles memory isolation |

### Interactive confirm (UC-04/05)

```python
h = UserCaseHarness(temp_dir, monkeypatch, config_overrides={
    "auto_allow_threshold": "medium",  # HIGH terminal still prompts
    "confirmation_timeout": 5,
})
h.auto_confirm(ConfirmationChoice.ALLOW_ONCE)  # or DENY
await h.setup()
```

### Plan mode (UC-10)

```python
result = await harness.run("...", mode="plan_and_execute")
# First LLM turn = plan JSON (≥3 steps); plan_review_enabled=False auto-executes
result.assert_plan_generated(min_steps=3)
result.assert_plan_completed()
```

### Surfaces

- **Slash** (`FakeAgentHost` + `AgentCommands`): `/mode`, `/status`
- **Gateway**: `chat_completions(..., registry=…)` with harness agent (not full FastAPI stack)
- **Telegram**: `TelegramApprovals` + callback tokens against real `ActionGuard`
- **Isolation**: two `UserCaseHarness` instances under separate temp roots / `profile_name`
