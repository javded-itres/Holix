# Contributing to Holix

Thank you for contributing. This document covers local setup, conventions, and how to submit changes.

## Development setup

```bash
git clone https://github.com/javded-itres/Holix.git
cd Holix
uv sync --all-extras
uv pip install -e ".[all]"
cp .env.example .env
holix doctor
```

Run tests:

```bash
uv run pytest
uv run pytest -m "not llm"
uv run pytest tests/test_agent_events.py
```

Lint (same scope as CI):

```bash
./scripts/lint.sh
# or:
uv run ruff check core cli api integrations tests
uv run ruff format --check core cli api integrations tests
```

**Git hooks (required for push):** after clone, install once:

```bash
./scripts/install-git-hooks.sh
```

This installs `pre-commit` (auto-fix on commit) and **pre-push** (full ruff gate — push fails if lint fails). See [RULES.md](RULES.md) §9.

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

Mandatory patterns (architecture, extensions, security, deploy, PR checklist): **[RULES.md](RULES.md)**.

- Python **3.12+**, async-first for agent code
- Profiles and user data under `~/.holix/profiles/`, not in the repo
- New tools extend `BaseTool` in `core/tools/`
- Agent behavior changes should go through graph/events (`core/graph/`, `core/agent_events.py`); prefer not growing the legacy loop
- Product features (billing, Studio extras, metrics UIs) → **extensions**, not `core/`
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
- `holix version` and `holix doctor` output (redact secrets)
- Steps to reproduce
- Expected vs actual behavior

## Documentation

- English (primary): `docs/en/`
- Russian: `docs/ru/`
- Index: [docs/README.md](docs/README.md)

Do not add new top-level doc trees without updating `docs/en/README.md` and `docs/ru/README.md`.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.