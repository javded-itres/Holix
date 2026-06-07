# Contributing to Helix

Thank you for contributing. This document covers local setup, conventions, and how to submit changes.

## Development setup

```bash
git clone https://github.com/YOUR_ORG/helix.git
cd helix
uv sync
uv pip install -e .
cp .env.example .env
helix doctor
```

Run tests:

```bash
uv run pytest
uv run pytest -m "not llm"
uv run pytest tests/test_agent_events.py
```

Lint:

```bash
uv run ruff check core cli api tests
```

## Project layout

| Package | Role |
|---------|------|
| `core/` | Agent, execution loop, tools, memory, skills, models |
| `cli/` | Typer CLI, TUI, doctor, gateway supervisor |
| `api/` | FastAPI gateway |
| `integrations/` | External integrations |
| `tests/` | Pytest suite |

Architecture overview: [docs/en/ARCHITECTURE.md](docs/en/ARCHITECTURE.md).

## Conventions

- Python **3.14+**, async-first for agent code
- Profiles and user data under `~/.helix/profiles/`, not in the repo
- New tools extend `BaseTool` in `core/tools/`
- Agent behavior changes should go through `core/agent_execution.py` and events in `core/agent_events.py`
- Document user-facing CLI changes in `docs/en/CLI.md` and `docs/ru/CLI.md`

## Pull requests

1. Fork and create a feature branch from `main` (or the active default branch).
2. Keep changes focused; avoid unrelated refactors.
3. Add or update tests for behavior changes.
4. Update bilingual docs when CLI, config, or install steps change.
5. Ensure `uv run pytest -m "not llm"` passes locally.

## Reporting issues

Include:

- OS and Python version (`python --version`)
- `helix version` and `helix doctor` output (redact secrets)
- Steps to reproduce
- Expected vs actual behavior

## Documentation

- English (primary): `docs/en/`
- Russian: `docs/ru/`
- Index: [docs/README.md](docs/README.md)

Do not add new top-level doc trees without updating `docs/en/README.md` and `docs/ru/README.md`.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.