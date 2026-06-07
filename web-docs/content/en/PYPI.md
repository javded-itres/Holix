# Publishing to PyPI

This guide covers packaging, naming, and releasing **Helix** on [PyPI](https://pypi.org).

## Package name

The PyPI distribution name is **`HelixAgentAi`** (not `helix` — that name is used by another project).

| Name on PyPI | Status |
|--------------|--------|
| `helix` | Taken (MIT LL mutation framework) |
| `helix-ai` | Taken (ML toolkit) |
| `helix-agent` | Available (not used) |
| **`HelixAgentAi`** | Used by this project |

Install:

```bash
pipx install HelixAgentAi
# or inside a venv:
pip install HelixAgentAi
pip install "HelixAgentAi[telegram,browser,tui-web]"
```

The console command is **`helix`** (registered via `[project.scripts]` → `cli.main:main`).  
It is placed in the environment’s `bin` directory (`venv/bin`, `~/.local/bin`, or pipx’s path). Activate the venv or use **pipx** / **uv tool** so `helix` is on your PATH from any directory.

Do not run `pip install helix` — that installs an unrelated package on PyPI.

Update `PYPI_PACKAGE` in `cli/installer/update.py` if the distribution name changes.

## Prerequisites

1. **PyPI account** — register at [pypi.org](https://pypi.org/account/register/)
2. **Trusted publishing** (recommended) or **API token**
   - Token: Account → API tokens → scope `HelixAgentAi` (after first upload) or entire account for first release
3. **Unique name** — confirm `HelixAgentAi` is free: `curl -s https://pypi.org/pypi/HelixAgentAi/json | head`
4. **Version** — bump in `pyproject.toml` and `cli/__init__.py` together
5. **Python 3.12+** — reflected in `requires-python`

## What is already configured

| Item | Location |
|------|----------|
| Build backend | `hatchling` in `pyproject.toml` |
| Packages | `cli`, `core`, `api`, `integrations` |
| Root settings module | `config.py` (force-included in wheel) |
| Console script | `helix = cli.main:main` |
| Extras | `browser`, `telegram`, `voice`, `tui-web`, `windows`, `all` |
| License | `LICENSE` + `license-files` |

## Local build check

```bash
uv sync --group dev
rm -rf dist
HELIX_NO_VERSION_BUMP=1 uv build --no-sources
ls -la dist/
# helixagentai-0.1.0-py3-none-any.whl
# helixagentai-0.1.0.tar.gz
```

Verify install in a clean venv:

```bash
uv venv /tmp/helix-test --python 3.12
uv pip install --python /tmp/helix-test/bin/python dist/helixagentai-*.whl
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
pip install -i https://test.pypi.org/simple/ HelixAgentAi
```

### 2. Production PyPI

```bash
uv build
uv publish dist/*
# or:
python -m twine upload dist/*
```

PyPI **no longer accepts account passwords**. Use an **API token** (or Trusted Publishing in CI).

1. [pypi.org](https://pypi.org) → Account settings → **API tokens** → Add token (scope: project `HelixAgentAi` or entire account for first upload).
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

## GitHub Actions (recommended)

Workflow: [`.github/workflows/publish-pypi.yml`](../../.github/workflows/publish-pypi.yml)

Two jobs: **build** (wheel + `twine check` + smoke install) → **publish** (OIDC to PyPI).

Triggers:

| Trigger | When |
|---------|------|
| `push` tag `v*` | Production release (uses environment `pypi`, Trusted Publishing) |
| `workflow_dispatch` | Manual run; optional TestPyPI dry run |

### One-time setup

**1. GitHub environments**

Repository → **Settings** → **Environments**:

| Name | Purpose |
|------|---------|
| `pypi` | Production uploads |
| `testpypi` | Optional TestPyPI dry runs |

Add protection rules (required reviewers) if you want approval before publish.

**2. PyPI Trusted Publishing**

On [pypi.org](https://pypi.org) → account → **Publishing** (or project **HelixAgentAi** after first upload) → **Add a new publisher**:

| Field | Value |
|-------|-------|
| PyPI project name | `HelixAgentAi` |
| Owner | `javded-itres` |
| Repository name | `HelixAgent` |
| Workflow filename | `publish-pypi.yml` |
| Environment name | `pypi` |

Repeat on [test.pypi.org](https://test.pypi.org) with environment `testpypi` if you use TestPyPI.

**3. (Optional) API token fallback**

Only if Trusted Publishing is not configured:

- GitHub secret `PYPI_API_TOKEN` or `TEST_PYPI_API_TOKEN` = full token (`pypi-...`)
- Manual run → choose **auth: api-token**

### Release via GitHub

```bash
# version already bumped in pyproject.toml + cli/__init__.py
git tag v0.1.3
git push origin v0.1.3
```

The workflow checks that tag `v0.1.3` matches `version = "0.1.3"` in `pyproject.toml`, builds, validates, and publishes.

**Manual run:** Actions → **Publish to PyPI** → Run workflow

- `testpypi: true` — upload to TestPyPI (environment `testpypi`)
- `auth: trusted-publishing` — default, no secrets
- `auth: api-token` — use `PYPI_API_TOKEN` / `TEST_PYPI_API_TOKEN` secrets

After publish:

```bash
pipx install HelixAgentAi
helix version
```

## Checklist before every release

- [ ] Version bumped in `pyproject.toml` and `cli/__init__.py`
- [ ] `uv build` succeeds
- [ ] Wheel installs in clean 3.12 venv; `helix --help` works
- [ ] `from config import settings` works (packaged `config.py`)
- [x] README and repository URLs updated
- [ ] Tests pass (`pytest -m "not llm"`)
- [ ] CHANGELOG updated
- [ ] TestPyPI smoke test (first times)
- [ ] Git tag matches version

## User-facing install docs

After publish, update:

- [INSTALLATION.md](INSTALLATION.md) — `pip install HelixAgentAi`
- Root [README.md](../../README.md)
- `helix update --channel pypi` (uses `HelixAgentAi` package name)

## Known limitations

- **Heavy core dependencies** — ChromaDB, LangGraph; first install may be slow
- **Optional extras** — Telegram, browser, voice, and web TUI require `pip install "HelixAgentAi[all]"` (or specific extras)
- **Playwright** — `browser` extra requires `playwright install chromium` after pip install
- **No bundled `.env.example` in wheel** — document copying from GitHub or `helix doctor`

## Related

- [INSTALLATION.md](INSTALLATION.md)
- [CONTRIBUTING.md](../../CONTRIBUTING.md)