# Live LLM scenarios

Real provider calls (not `ScriptedLLM`). Artifacts go under per-test temp dirs and are **deleted** after each test unless `HOLIX_LIVE_KEEP_ARTIFACTS=1`.

## Run

```bash
# recommended
./scripts/test_live_llm.sh

# equivalent
HOLIX_LIVE_LLM=1 uv run python -m pytest tests/live_llm -m live_llm -vv --tb=short
```

Default CI (`pytest -m "not llm"`) **never** runs these.

## Provider config

Priority:

1. `HOLIX_LIVE_MODEL` / `HOLIX_LIVE_BASE_URL` / `HOLIX_LIVE_API_KEY`
2. Holix `settings` (`model`, `base_url`, `api_key` from env / `.env`)
3. If `HOLIX_LIVE_LLM=1` and nothing else: Ollama defaults `http://localhost:11434/v1`

Examples:

```bash
# Ollama
export HOLIX_LIVE_MODEL=llama3.2
export HOLIX_LIVE_BASE_URL=http://localhost:11434/v1
export HOLIX_LIVE_API_KEY=ollama
./scripts/test_live_llm.sh

# OpenAI-compatible
export HOLIX_LIVE_MODEL=gpt-4o-mini
export HOLIX_LIVE_BASE_URL=https://api.openai.com/v1
export HOLIX_LIVE_API_KEY=sk-...
./scripts/test_live_llm.sh -k "live_01 or live_11"
```

Session starts with a **probe** (`PONG`). If unreachable → skip (or fail when `HOLIX_LIVE_LLM=1`).

## Options

| Env | Meaning |
|-----|---------|
| `HOLIX_LIVE_LLM=1` | Force run (fail if probe fails) |
| `HOLIX_LIVE_LLM=0` | Force skip |
| `HOLIX_LIVE_KEEP_ARTIFACTS=1` | Keep workspace copy under tmp artifacts (pytest tmp path) |
| `-k live_30` | Run subset by name |
| `-m "live_llm and not slow"` | Skip web/browser slow tests |

## Coverage (~30 tests)

| Group | IDs | Topics |
|-------|-----|--------|
| Q&A | 01–05 | math, knowledge, RU, multi-turn, JSON |
| Files | 10–15 | read/write/list/edit multi-file |
| Terminal / confirm | 20–24 | echo, dirs, allow/deny, block `rm -rf` |
| Projects | 30–35 | Python app, FastAPI stub, CLI, JSON, plan mode, refactor |
| Web / browser | 40–43 | search, research report, optional Playwright |
| Code / hybrid | 50–55 | explain, bugfix, hybrid, logs, math, Dockerfile |

## Notes

- Workspace jail + isolated `data/` / DBs per test; wiped in fixture teardown.
- Meta-agent, reflexion, subagents, MCP off for cost/stability.
- Live answers are flaky by nature — asserts use soft keyword checks + filesystem side effects.
