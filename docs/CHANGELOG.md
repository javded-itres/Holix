# Changelog

## 0.1.3 — 2026-06-07

### Added
- **web-docs** — dark documentation site with search, EN/RU, mobile layout (`helix docs`)
- **Gateway docs companion** — optional `--with-docs` / `HELIX_GATEWAY_WITH_DOCS`
- Auto-seed `~/.helix/.env` and `.env.example` on first `HELIX_HOME` setup
- Hatch build hook for patch version bump on `uv build` (`HELIX_NO_VERSION_BUMP=1` to disable)

### Security
- Shared permission manager, gateway auth hardening, SSRF checks, subagent API key via env, chat locking

### Fixed
- web-docs routing for in-page TOC anchors, home route (`#/`), mobile search and sidebar menu

## Unreleased

### Added
- **Telegram voice messages** — Whisper transcription for voice notes and audio attachments (`OPENAI_API_KEY`)
- **`helix logs`** — unified log viewer (agent, sub-agent, gateway, cron, system); filters, follow, rotation, `debug on|off|status` — [docs/en/LOGS.md](en/LOGS.md)
- Centralized logging under `{HELIX_HOME}/logs/` (`agent.jsonl`, `subagent.jsonl`, `helix.log`, debug JSONL)
- **`helix cron`** — profile cron jobs with gateway scheduler, TUI manager, Telegram, bundled `helix-cron` skill
- Cross-platform support: `HELIX_HOME` / XDG / `%LOCALAPPDATA%`, Windows terminal whitelist, optional `windows` extra (`psutil`), CI matrix (linux/windows/macos)
- Per-session model persistence (`/models`, Telegram picker)
- TUI GitHub-style file diffs; MCP path validation before spawn
- PyPI packaging: distribution `helix-agent`, build fixes, [docs/en/PYPI.md](en/PYPI.md)
- GitHub workflow `.github/workflows/publish-pypi.yml` (manual)
- Full CLI reference: `docs/en/CLI.md`, `docs/ru/CLI.md`
- Slash command reference: `docs/en/SLASH_COMMANDS.md`, `docs/ru/SLASH_COMMANDS.md`
- Installation guide: `docs/en/INSTALLATION.md`, `docs/ru/INSTALLATION.md`
- Browser tools (active): `docs/en/BROWSER_TOOLS.md`
- `LICENSE`, `CONTRIBUTING.md`, GitHub-ready root `README.md`
- `docs/archive/README.md` — marks obsolete docs as historical
- Production settings in `config.py` (gateway, security, tools, Telegram)
- `helix doctor` with `--fix` and LLM config repair
- `helix gateway start|stop|status|reload` background supervisor
- Gateway: admin auth always required; optional auth for `/v1/*`
- Prometheus `/metrics` endpoint
- Terminal command whitelist enforcement
- Profile secret placeholders `${VAR}` / `${ENV:VAR}`
- CI (GitHub Actions), pre-commit, systemd unit example
- Bilingual docs: `docs/en/`, `docs/ru/`

### Changed
- Gateway bind default `127.0.0.1`; CORS from `HELIX_CORS_ORIGINS`
- API keys: HMAC-SHA256 with `HELIX_API_KEY_PEPPER`
- Docker uses `helix gateway start`

### Removed
- Root `cli.py`, `main.py` (dead entry points)
- `helix models-legacy` command
- Obsolete docs (merged into `docs/en/` and `docs/ru/`)