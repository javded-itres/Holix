# Holix Extensions — Author Guide

> **SDK API version:** `holix_sdk.__api_version__ == 1`

This guide explains how to build Holix extensions using the **`holix-sdk`** package — a **separate, installable Python package** with a stable public API. Extension authors should depend on `holix-sdk`, not on internal `core.*` or `cli.*` modules.

Related docs:

- [BUILD_WITHOUT_HOLIX.md](BUILD_WITHOUT_HOLIX.md) — external apps via HTTP/MCP (no Python import)
- [EXTENSION_GATEWAY.md](EXTENSION_GATEWAY.md) — gateway contract for host extensions
- [GATEWAY_API.md](GATEWAY_API.md) — full HTTP reference

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Holix core (MIT) — agent, CLI, gateway, extension loader │
└───────────────────────────┬─────────────────────────────┘
                            │
              ┌─────────────▼─────────────┐
              │   holix-sdk (MIT, PyPI)    │  ← import ONLY this
              │   stable extension API     │
              └─────────────┬───────────────┘
                            │
     ┌──────────────────────┼──────────────────────┐
     │                      │                      │
holix.extensions    holix.agent.extensions    HTTP / MCP
(host: CLI, HTTP)   (tools, slash, prompts)   (any language)
```

| Pattern | Entry-point group | Typical use |
|---------|-------------------|-------------|
| **Host extension** | `holix.extensions` | CLI subcommands, FastAPI routes, sidecar UI |
| **Agent extension** | `holix.agent.extensions` | Agent tools, slash commands, prompt fragments |
| **External application** | — | Mobile, web, SaaS via Gateway API |

Built-in host extensions in Holix core: `telegram`, `max`.  
Reference agent extension in the Holix repo: `packages/holix-extension-demo`.  
Reference host extension (separate repo): [holix-studio](https://github.com/javded-itres/holix-studio).

---

## holix-sdk — separate package

`holix-sdk` lives in `packages/holix-sdk/` in the Holix repository and is published **independently** from Holix core.

### Install

```bash
# End users / extension authors
pip install holix-sdk Holix

# Holix monorepo developers
uv sync --extra sdk
```

### Why a separate package?

1. **Stable contract** — breaking changes only in `holix-sdk` major versions.
2. **Clear boundary** — host/UI code never imports `core.*` or `cli.*`.
3. **Independent release** — extension authors pin `holix-sdk>=0.1.0` without forking Holix.
4. **License clarity** — `holix-sdk` is MIT, same as Holix core.

### Public modules

| Module | Import | Purpose |
|--------|--------|---------|
| `holix_sdk` | `HolixExtension`, `ExtensionBase`, `ExtensionContext`, `CAPABILITY_*` | Host extension protocol |
| `holix_sdk.agent` | `AgentExtensionBase`, `SlashCommandSpec` | Agent extension protocol |
| `holix_sdk.host` | `AgentCommands`, `all_slash_commands`, … | Bridge host UI to agent |
| `holix_sdk.i18n` | `LocaleStore`, `t`, `host_locale` | Localization |
| `holix_sdk.models` | `ModelChoice`, `build_models_menu`, … | Runtime model picker |
| `holix_sdk.profile` | `ProfileManager`, `init_profile` | Profile access |
| `holix_sdk.agent_runtime` | `HolixAgent`, agent events | Agent lifecycle & events |
| `holix_sdk.security` | confirmation, web security helpers | Approvals & tokens |
| `holix_sdk.commands` | `command_specs` | Host command menu |
| `holix_sdk.paths` | `realpath_under`, … | Safe paths |

Check API version in code:

```python
from holix_sdk import __api_version__
assert __api_version__ == 1
```

---

## Create a new extension — step by step

### 1. Choose extension type

| Goal | Type | Entry point |
|------|------|-------------|
| Add `holix mycmd` CLI | Host | `holix.extensions` |
| Mount routes on gateway `:8000` | Host | `holix.extensions` |
| Add agent tool | Agent | `holix.agent.extensions` |
| Add `/mycommand` slash | Agent | `holix.agent.extensions` |
| Inject system prompt text | Agent | `holix.agent.extensions` |

One Python package can register **both** entry points.

### 2. Project layout

```
my-holix-extension/
├── pyproject.toml
├── README.md
├── LICENSE
├── my_holix_ext/
│   ├── __init__.py
│   ├── holix.plugin.json      # optional manifest
│   ├── extension.py           # host entry (holix.extensions)
│   ├── agent.py               # agent entry (holix.agent.extensions)
│   └── tools.py               # agent tools (if any)
└── tests/
    └── test_extension.py
```

### 3. `pyproject.toml`

**Agent extension only:**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "my-holix-extension"
version = "0.1.0"
description = "My Holix agent extension"
readme = "README.md"
license = "MIT"
requires-python = ">=3.12"
dependencies = [
    "Holix>=0.1.21",
    "holix-sdk>=0.1.0",
]

[project.entry-points."holix.agent.extensions"]
myext = "my_holix_ext.agent:get_agent_extension"

[tool.hatch.build.targets.wheel]
packages = ["my_holix_ext"]
```

**Host extension** — add:

```toml
[project.entry-points."holix.extensions"]
myext = "my_holix_ext.extension:get_extension"
```

**Optional FastAPI dependency** for HTTP routes:

```toml
dependencies = [
    "Holix>=0.1.21",
    "holix-sdk>=0.1.0",
    "fastapi>=0.136.0",
]
```

### 4. `holix.plugin.json` (optional)

Place inside the Python package directory (e.g. `my_holix_ext/holix.plugin.json`):

```json
{
  "id": "myext",
  "version": "0.1.0",
  "requires": { "holix": ">=0.1.21", "holix_sdk": ">=0.1.0" },
  "description": "Short human-readable description",
  "capabilities": ["agent"],
  "permissions": ["tools"]
}
```

Capabilities: `cli`, `http`, `sidecar`, `agent`.  
Holix merges manifest fields when the extension class leaves defaults empty.

### 5. Implement agent extension

```python
# my_holix_ext/agent.py
from __future__ import annotations

from typing import Any

from holix_sdk.agent import AgentExtensionBase, SlashCommandSpec
from core.tools.base import BaseTool

from my_holix_ext.tools import MyTool


class MyAgentExtension(AgentExtensionBase):
    name = "myext"
    version = "0.1.0"
    requires_holix = ">=0.1.21"
    permissions = frozenset({"tools"})

    def register_tools(self, registry: Any, agent: Any) -> None:
        registry.register(MyTool())

    def register_slash_commands(self, commands: list[SlashCommandSpec]) -> None:
        commands.append(SlashCommandSpec("/myext", "My extension command"))

    def augment_system_prompt(self, profile: str) -> str | None:
        return "## My extension\nExtra instructions for the agent."


def get_agent_extension() -> MyAgentExtension:
    return MyAgentExtension()
```

**Tool example** (`core.tools.base.BaseTool` is allowed inside agent extensions):

```python
# my_holix_ext/tools.py
from __future__ import annotations

from typing import Any

from core.tools.base import BaseTool


class MyTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "my_tool"
        self.description = "Does something useful."
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }

    async def execute(self, query: str, **kwargs: Any) -> str:
        return f"Result for: {query}"
```

### 6. Implement host extension

```python
# my_holix_ext/extension.py
from __future__ import annotations

from typing import Any

import typer
from holix_sdk import CAPABILITY_CLI, CAPABILITY_HTTP, ExtensionBase


class MyExtension(ExtensionBase):
    name = "myext"
    version = "0.1.0"
    requires_holix = ">=0.1.21"
    description = "My host extension"
    capabilities = frozenset({CAPABILITY_CLI, CAPABILITY_HTTP})
    permissions = frozenset({"gateway", "network"})

    def register_cli(self, root: typer.Typer) -> None:
        from my_holix_ext.cli import app
        root.add_typer(app, name="myext")

    def mount_gateway(self, app: Any) -> None:
        from my_holix_ext.router import router
        app.include_router(router, prefix="/myext")


def get_extension() -> MyExtension:
    return MyExtension()
```

**Rules for host code:**

- Import **`holix_sdk`** for protocols, host bridge, i18n, models.
- Do **not** import `core.*`, `cli.*`, `integrations.*` (except `core.tools.base` is agent-only).
- Use FastAPI / Typer in **your** package, not in Holix internals.

### 7. Install and verify

```bash
# Editable install while developing
pip install -e ./my-holix-extension

# Or from monorepo workspace (if linked)
uv sync

# Verify discovery
holix extensions list
holix extensions agent-list
holix extensions list --json
```

Run the agent and confirm the tool appears:

```bash
holix chat-command -p default
# Agent should list my_tool among registered tools
```

### 8. Test

```python
# tests/test_extension.py
from my_holix_ext.agent import get_agent_extension


def test_agent_extension_metadata() -> None:
    ext = get_agent_extension()
    assert ext.name == "myext"
    assert "tools" in ext.permissions
```

Run: `pytest tests/ -q`

---

## Permissions

Declare only what you need in `permissions` (code or manifest):

| Permission | Required for |
|------------|--------------|
| `tools` | Registering agent tools |
| `gateway` | `mount_gateway()` — FastAPI routes on Holix gateway |
| `network` | Outbound HTTP, messengers, sidecar servers |
| `filesystem` | Workspace file APIs in host |
| `subprocess` | Spawning child processes |

Holix logs a warning and **skips** registration if permissions are missing.

---

## CLI commands

```bash
holix extensions list           # host extensions (holix.extensions)
holix extensions agent-list     # agent extensions (holix.agent.extensions)
holix extensions list --json    # machine-readable output
```

---

## Publishing

### Publish `holix-sdk` (maintainers)

From `packages/holix-sdk/`:

```bash
uv build
uv publish   # or twine upload dist/*
```

Package name on PyPI: **`holix-sdk`**.

### Publish your extension

1. Set `name`, `version`, `dependencies` in `pyproject.toml`.
2. Pin `holix-sdk>=0.1.0` and `Holix>=0.1.21`.
3. `uv build && uv publish`.
4. Users install: `pip install my-holix-extension`.

Holix discovers the extension automatically via entry points after `pip install` — no changes to Holix core required.

---

## Checklist before release

- [ ] Host code imports only `holix_sdk` (not `core` / `cli`)
- [ ] Entry-point factory functions return instances (`get_extension()`, `get_agent_extension()`)
- [ ] `name`, `version`, `requires_holix`, `permissions` set on extension class
- [ ] `holix.plugin.json` present (recommended)
- [ ] `holix extensions list` / `agent-list` shows your package
- [ ] Tests pass
- [ ] License file included (MIT for open extensions)

---

## Licensing

| Component | License |
|-----------|---------|
| Holix core | MIT |
| holix-sdk | MIT |
| Your MIT extension | Your choice (MIT recommended) |
| Proprietary products (e.g. Holix Studio) | Separate license |

See [THIRD_PARTY_LICENSES.md](../../THIRD_PARTY_LICENSES.md).