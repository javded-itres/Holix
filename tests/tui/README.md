# Holix TUI tests (full launch)

Full **Textual Pilot** launch of `HolixCodeApp` — real compose/mount/bindings, mock agent (no LLM).

## Run

```bash
# recommended
./scripts/test_tui.sh

# equivalent
uv run python -m pytest tests/tui -m tui -v --tb=short

# single test
uv run python -m pytest tests/tui/test_tui_slash.py::test_tui_10_help_command -vv
```

Markers: `tui` + `integration`. Not the same as `live_llm`.

## What is covered

| ID | Check |
|----|--------|
| tui_01–03 | Launch, ready, widgets, prompt enabled |
| tui_10–14 | `/help`, `/mode`, `/status`, `/clear` |
| tui_20–22 | Send message → `agent.run`, empty enter, slash skips run |
| tui_30–31 | Confirmation modal allow/deny keys |
| tui_40 | Slash suggestions widget present |

## Architecture

- `TestableHolixCodeApp` overrides `_initialize_agent` with a mock agent.
- `app.run_test()` = full Textual app lifecycle (Pilotual Pilot).
- Isolated `HOLIX_HOME` from root `tests/conftest.py`.

## Optional: real agent (slow)

```python
async with launch_tui(use_real_agent=True) as (app, pilot):
    ...
```

Requires working LLM config (same as live suite). Prefer `tests/live_llm` for provider E2E.
