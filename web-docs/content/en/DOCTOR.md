# Helix Doctor

Diagnostics for profiles, LLM, gateway, Telegram, and security settings.

## Usage

```bash
helix doctor              # report only
helix doctor --fix        # safe fixes + LLM config repair
helix doctor --no-llm     # no LLM calls
helix -p work doctor
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

- `~/.helix` (or `HELIX_HOME`) writable
- **Platform:** OS, data path, `node`/`npx`/`uv`/`git` in PATH; Windows: psutil hint, terminal whitelist note
- Profile YAML and providers
- LLM endpoint and model availability
- Gateway stale state / health
- Telegram token and allowlist
- Production: pepper, CORS, auth, code executor

After fixes, inspect runtime logs: `helix logs -l error` — see [LOGS.md](LOGS.md).