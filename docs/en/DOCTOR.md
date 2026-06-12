# Holix Doctor

Diagnostics for profiles, LLM, gateway, Telegram, and security settings.

## Usage

```bash
holix doctor              # report only
holix doctor --fix        # safe fixes + LLM config repair
holix doctor --no-llm     # no LLM calls; skips live endpoint probe (CI-safe)
holix -p work doctor
```

## Without `--fix`

- Lists errors, warnings, recommendations
- Optional LLM action plan (unless `--no-advice`)

## With `--fix`

Deterministic fixes:

- Create profile directories
- Fix paths, stale gateway state, default provider/model

LLM fixes (default profile LLM):

- Invalid `config.yaml` / validation errors (backup: `config.yaml.bak`)

## Checks

- `~/.holix` (or `HOLIX_HOME`) writable
- **Platform:** OS, data path, `node`/`npx`/`uv`/`git` in PATH; Windows: psutil hint, terminal whitelist note
- Profile YAML and providers
- LLM endpoint and model availability (skipped with `--no-llm`)
- Gateway stale state / health
- Holix Link connections (count, online/offline when gateway runs)
- Telegram token, access requests, and allowlist
- Production: pepper, CORS, auth, code executor

After fixes, inspect runtime logs: `holix logs -l error` — see [LOGS.md](LOGS.md).