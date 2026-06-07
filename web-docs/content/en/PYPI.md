# Publishing to PyPI

This guide covers packaging, naming, and releasing **Helix** on [PyPI](https://pypi.org).

## Package name

The PyPI distribution name is **`helix-agent-ai`** (HelixAgentAi; not `helix` or the taken name `helix-agent`).

| Name on PyPI | Status |
|--------------|--------|
| `helix` | Taken (MIT LL mutation framework) |
| `helix-ai` | Taken (ML toolkit) |
| **`helix-agent-ai`** | Used by this project (verify before first upload) |

Install:

```bash
pipx install helix-agent-ai
# or inside a venv:
pip install helix-agent-ai
pip install "helix-agent-ai[telegram,browser,tui-web]"
```

The console command is **`helix`** (registered via `[project.scripts]` → `cli.main:main`).  
It is placed in the environment’s `bin` directory (`venv/bin`, `~/.local/bin`, or pipx’s path). Activate the venv or use **pipx** / **uv tool** so `helix` is on your PATH from any directory.

Do not run `pip install helix` — that installs an unrelated package on PyPI.

Update `PYPI_PACKAGE` in `cli/installer/update.py` if the distribution name changes.

## Prerequisites

1. **PyPI account** — register at [pypi.org](https://pypi.org/account/register/)
2. **Trusted publishing** (recommended) or **API token**
   - Token: Account → API tokens → scope `helix-agent-ai` (after first upload) or entire account for first release
3. **Unique name** — confirm `helix-agent-ai` is free: `curl -s https://pypi.org/pypi/helix-agent-ai/json | head`
4. **Version** — bump in `pyproject.toml` and `cli/__init__.py` together
5. **Python 3.14+** — reflected in `requires-python`; PyPI users need 3.14

## What is already configured

| Item | Location |
|------|----------|
| Build backend | `hatchling` in `pyproject.toml` |
| Packages | `cli`, `core`, `api`, `integrations` |
| Root settings module | `config.py` (force-included in wheel) |
| Console script | `helix = cli.main:app` |
| Extras | `browser`, `telegram`, `tui-web`, `all` |
| License | `LICENSE` + `license-files` |

## Local build check

```bash
uv sync --group dev
rm -rf dist
uv build
ls -la dist/
# helix_agent_ai-0.1.0-py3-none-any.whl
# helix_agent_ai-0.1.0.tar.gz
```

Verify install in a clean venv:

```bash
uv venv /tmp/helix-test --python 3.14
uv pip install --python /tmp/helix-test/bin/python dist/helix_agent_ai-*.whl
/tmp/helix-test/bin/helix version
/tmp/helix-test/bin/python -c "from config import settings; print('ok')"
```

Run tests before release:

```bash
uv run pytest -m "not llm"
```

## First release (TestPyPI, then production)

### 1. TestPyPI (recommended)

```bash
uv build
uv publish --publish-url https://test.pypi.org/legacy/ dist/*
# or:
python -m twine upload --repository testpypi dist/*
```

Test install:

```bash
pip install -i https://test.pypi.org/simple/ helix-agent-ai
```

### 2. Production PyPI

```bash
uv build
uv publish dist/*
# or:
python -m twine upload dist/*
```

PyPI **no longer accepts account passwords**. Use an **API token** (or Trusted Publishing in CI).

1. [pypi.org](https://pypi.org) → Account settings → **API tokens** → Add token (scope: project `helix-agent-ai` or entire account for first upload).
2. Publish locally:

```bash
# option A (recommended for uv)
export UV_PUBLISH_TOKEN='pypi-AgENdXNlcm5hbWU6...'
uv publish dist/*

# option B (twine-compatible)
export UV_PUBLISH_USERNAME=__token__
export UV_PUBLISH_PASSWORD='pypi-AgENdXNlcm5hbWU6...'
uv publish dist/*
```

Never commit tokens. Do **not** enter your PyPI account password when `uv` prompts — that causes `403 Username/Password authentication is no longer supported`.

## Versioning

1. Edit `version` in `pyproject.toml`
2. Edit `cli/__init__.py` → `__version__`
3. Add entry to `docs/CHANGELOG.md`
4. Git tag: `git tag v0.1.0 && git push origin v0.1.0`

PyPI does not allow re-uploading the same version.

## GitHub Actions (optional)

See `.github/workflows/publish-pypi.yml` (manual `workflow_dispatch`).

**Option A — Trusted Publishing (recommended):**

1. Create project `helix-agent-ai` on PyPI (first upload may require token once).
2. PyPI → project → **Publishing** → **Add a new publisher**:
   - Owner: `javded-itres`
   - Repository: `HelixAgent`
   - Workflow: `publish-pypi.yml`
   - Environment: `pypi`
3. GitHub → repo → Settings → Environments → create **`pypi`** (optional protection rules).
4. Run workflow **Publish to PyPI** — no `PYPI_API_TOKEN` secret needed when OIDC is configured.

**Option B — API token secret:**

- GitHub secret `PYPI_API_TOKEN` = full token string (`pypi-...`)
- Workflow sets `UV_PUBLISH_TOKEN` automatically

## Checklist before every release

- [ ] Version bumped in `pyproject.toml` and `cli/__init__.py`
- [ ] `uv build` succeeds
- [ ] Wheel installs in clean 3.14 venv; `helix --help` works
- [ ] `from config import settings` works (packaged `config.py`)
- [x] README and repository URLs updated
- [ ] Tests pass (`pytest -m "not llm"`)
- [ ] CHANGELOG updated
- [ ] TestPyPI smoke test (first times)
- [ ] Git tag matches version

## User-facing install docs

After publish, update:

- [INSTALLATION.md](INSTALLATION.md) — `pip install helix-agent-ai`
- Root [README.md](../../README.md)
- `helix update --channel pypi` (uses `helix-agent-ai` package name)

## Known limitations

- **Python 3.14 only** — narrow audience until you lower `requires-python` and test on 3.12/3.13
- **Heavy dependencies** — ChromaDB, LangGraph; first install may be slow
- **Playwright** — `browser` extra requires `playwright install chromium` after pip install
- **No bundled `.env.example` in wheel** — document copying from GitHub or `helix doctor`

## Related

- [INSTALLATION.md](INSTALLATION.md)
- [CONTRIBUTING.md](../../CONTRIBUTING.md)