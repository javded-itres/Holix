# Publishing to PyPI

This guide covers packaging, naming, and releasing **Helix** on [PyPI](https://pypi.org).

## Package name

The PyPI distribution name is **`helix-agent`** (not `helix`).

| Name on PyPI | Status |
|--------------|--------|
| `helix` | Taken (MIT LL mutation framework) |
| `helix-ai` | Taken (ML toolkit) |
| **`helix-agent`** | Used by this project (verify before first upload) |

Install:

```bash
pipx install helix-agent
# or inside a venv:
pip install helix-agent
pip install "helix-agent[telegram,browser,tui-web]"
```

The console command is **`helix`** (registered via `[project.scripts]` → `cli.main:main`).  
It is placed in the environment’s `bin` directory (`venv/bin`, `~/.local/bin`, or pipx’s path). Activate the venv or use **pipx** / **uv tool** so `helix` is on your PATH from any directory.

Do not run `pip install helix` — that installs an unrelated package on PyPI.

Update `PYPI_PACKAGE` in `cli/installer/update.py` if the distribution name changes.

## Prerequisites

1. **PyPI account** — register at [pypi.org](https://pypi.org/account/register/)
2. **Trusted publishing** (recommended) or **API token**
   - Token: Account → API tokens → scope `helix-agent` (after first upload) or entire account for first release
3. **Unique name** — confirm `helix-agent` is free: `curl -s https://pypi.org/pypi/helix-agent/json | head`
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
# helix_agent-0.1.0-py3-none-any.whl
# helix_agent-0.1.0.tar.gz
```

Verify install in a clean venv:

```bash
uv venv /tmp/helix-test --python 3.14
uv pip install --python /tmp/helix-test/bin/python dist/helix_agent-*.whl
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
pip install -i https://test.pypi.org/simple/ helix-agent
```

### 2. Production PyPI

```bash
uv build
uv publish dist/*
# or:
python -m twine upload dist/*
```

Use environment variables (never commit tokens):

```bash
export UV_PUBLISH_USERNAME=__token__
export UV_PUBLISH_PASSWORD=pypi-AgEIcHlwaS5vcmcC...
```

## Versioning

1. Edit `version` in `pyproject.toml`
2. Edit `cli/__init__.py` → `__version__`
3. Add entry to `docs/CHANGELOG.md`
4. Git tag: `git tag v0.1.0 && git push origin v0.1.0`

PyPI does not allow re-uploading the same version.

## GitHub Actions (optional)

See `.github/workflows/publish-pypi.yml` (manual `workflow_dispatch`).

Secrets:

- `PYPI_API_TOKEN` — PyPI token with upload scope

Trusted publishing: connect the GitHub repo to PyPI project settings (no long-lived token).

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

- [INSTALLATION.md](INSTALLATION.md) — `pip install helix-agent`
- Root [README.md](../../README.md)
- `helix update --channel pypi` (uses `helix-agent` package name)

## Known limitations

- **Python 3.14 only** — narrow audience until you lower `requires-python` and test on 3.12/3.13
- **Heavy dependencies** — ChromaDB, LangGraph; first install may be slow
- **Playwright** — `browser` extra requires `playwright install chromium` after pip install
- **No bundled `.env.example` in wheel** — document copying from GitHub or `helix doctor`

## Related

- [INSTALLATION.md](INSTALLATION.md)
- [CONTRIBUTING.md](../../CONTRIBUTING.md)