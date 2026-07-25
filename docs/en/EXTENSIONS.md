# Holix Extensions

> **SDK API:** `holix_sdk.__api_version__ == 1`  
> Extensions are the supported way to add tools, slash commands, HTTP APIs, UI, and messenger plugins **without forking Holix core**.

This page covers architecture, extension types, permissions, install paths, **end-to-end examples**, drop-ins, sidecars, Telegram/MAX plugins, LLM middleware, CLI, and a release checklist.

Related: [MCP](MCP.md) · [API Gateway](GATEWAY.md) · [API reference](GATEWAY_API.md) · [Telegram](TELEGRAM.md) · [MAX](MAX.md) · [CLI](CLI.md)

---

## Why extensions

| Goal | Extension approach |
|------|--------------------|
| New agent tool | Agent extension + `BaseTool` |
| Slash `/mycommand` | Agent extension |
| `holix mycmd` CLI | Host extension (`register_cli`) |
| HTTP on gateway `:8000` | Host extension (`mount_gateway`) |
| Separate UI process | Host + capability `sidecar` |
| Billing / paywall (Telegram or MAX) | Host + `register_telegram` / `register_max` |
| Per-LLM-call stats | Agent + `register_middleware` |
| External SaaS / mobile | No Python — [Gateway API](GATEWAY_API.md) |

**Principle:** Holix core stays a MIT agent runtime; products (Studio, billing, custom tools) live in separate packages discovered via entry points or profile folders.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Holix core (MIT) — agent, CLI, gateway, extension loader    │
└──────────────────────────────┬───────────────────────────────┘
                               │
                 ┌─────────────▼─────────────┐
                 │  holix-sdk (MIT, PyPI)     │  ← import ONLY this (host)
                 │  stable public API         │
                 └─────────────┬─────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
 holix.extensions      holix.agent.extensions     HTTP / MCP
 (CLI, gateway,        (tools, slash, prompts,   (any language)
  sidecar, TG/MAX)      middleware, settings)
```

| Pattern | Entry point / path | Provides |
|---------|-------------------|----------|
| **Host** | `holix.extensions` | CLI, FastAPI routes, sidecar, `register_telegram` / `register_max` |
| **Agent** | `holix.agent.extensions` | Tools, slash, system prompt, LLM middleware, settings |
| **Drop-in** | `~/.holix/profiles/<p>/extensions/<name>/` | Same without pip; delete folder = unload |
| **Telegram plugin** | `holix.telegram.extensions` **or** host `register_telegram` | Bot commands, handlers, message gate, access check |
| **MAX plugin** | `holix.max.extensions` **or** host `register_max` | Same for MAX |
| **External app** | Bearer API key | Mobile/web/SaaS via gateway |

Built-in host extensions: `telegram`, `max`.  
Reference agent: `packages/holix-extension-demo`.  
Reference host UI: [holix-studio](https://github.com/javded-itres/holix-studio).  
Billing: `holix-telegram-billing`, `holix-max-billing`, `holix-billing-console`.

---

## Capabilities

| Capability | SDK constant | Purpose |
|------------|--------------|---------|
| `cli` | `CAPABILITY_CLI` | Typer subcommands (`holix <name> …`) |
| `http` | `CAPABILITY_HTTP` | Gateway routes (`mount_gateway`) |
| `sidecar` | `CAPABILITY_SIDECAR` | Companion process on `holix gateway start` |
| `agent` | (agent entry) | Tools / slash / prompt / middleware |

One package may register **both** host and agent entry points.

---

## Permissions

Declare the **minimum** set. Missing permissions → warning and **skipped** registration.

| Permission | Required for |
|------------|--------------|
| `tools` | Agent tools |
| `middleware` | LLM middleware chain |
| `gateway` | `mount_gateway()` |
| `network` | Outbound HTTP, messengers, sidecar |
| `filesystem` | Workspace file APIs (host) |
| `subprocess` | Child processes |

---

## holix-sdk

Separate package (`packages/holix-sdk/`, PyPI: **`holix-sdk`**). Host code must **not** import `core.*` / `cli.*`.

```bash
pip install holix-sdk Holix
# Holix monorepo:
uv sync --extra sdk
```

| Module | Purpose |
|--------|---------|
| `holix_sdk` | `ExtensionBase`, `ExtensionContext`, `CAPABILITY_*` |
| `holix_sdk.agent` | `AgentExtensionBase`, `SlashCommandSpec` |
| `holix_sdk.host` | Host UI ↔ agent bridge |
| `holix_sdk.i18n` | Localization |
| `holix_sdk.models` | Model picker |
| `holix_sdk.profile` | Profiles |
| `holix_sdk.agent_runtime` | Agent lifecycle |
| `holix_sdk.security` | Approvals, tokens |
| `holix_sdk.paths` | Safe paths |

```python
from holix_sdk import __api_version__
assert __api_version__ == 1
```

**Exception:** agent extensions may use `core.tools.base.BaseTool` and preferably `core.extensions.agent_base.AgentExtensionBase` (settings + middleware).

---

## Install / connect an extension

### 1. pip / uv (entry points)

```bash
pip install my-holix-extension
# development:
pip install -e ./my-holix-extension

holix extensions list
holix extensions agent-list
holix extensions list --json
```

### 2. Profile drop-in (no pip)

```text
~/.holix/profiles/default/extensions/my_stats/
  agent.py
  settings.default.yaml    # optional
  holix.plugin.json        # optional
  extension.py             # host optional
```

Also: `~/.holix/extensions/<name>/` and production symlinks under `/var/lib/holix/extensions/`.

### 3. Product env vars

```bash
HOLIX_BILLING_ENABLED=true
HOLIX_BILLING_PROVIDERS=stars,yookassa
HOLIX_MAX_BILLING_ENABLED=true
```

### 4. Verify

```bash
holix extensions list
holix extensions agent-list
holix extensions settings demo
holix doctor
holix gateway start -f
# OpenAPI: http://127.0.0.1:8000/docs
```

---

## Tutorial: agent extension (full example)

### Layout

```text
hello-holix-ext/
├── pyproject.toml
├── hello_holix_ext/
│   ├── __init__.py
│   ├── holix.plugin.json
│   ├── agent.py
│   └── tools.py
└── tests/test_extension.py
```

### `pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "hello-holix-ext"
version = "0.1.0"
description = "Sample Holix agent extension"
requires-python = ">=3.12"
dependencies = ["Holix>=0.1.21", "holix-sdk>=0.1.0"]

[project.entry-points."holix.agent.extensions"]
hello = "hello_holix_ext.agent:get_agent_extension"

[tool.hatch.build.targets.wheel]
packages = ["hello_holix_ext"]
```

### Tool

```python
# hello_holix_ext/tools.py
from __future__ import annotations
from typing import Any
from core.tools.base import BaseTool


class HelloEchoTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "hello_echo"
        self.description = "Demo echo tool from the hello extension."
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }

    async def execute(self, text: str = "", **kwargs: Any) -> str:
        return f"hello_echo: {text}"
```

### Agent entry

```python
# hello_holix_ext/agent.py
from __future__ import annotations
from typing import Any
from holix_sdk.agent import SlashCommandSpec

try:
    from core.extensions.agent_base import AgentExtensionBase
except ImportError:
    from holix_sdk.agent import AgentExtensionBase  # type: ignore

from hello_holix_ext.tools import HelloEchoTool


class HelloAgentExtension(AgentExtensionBase):
    name = "hello"
    version = "0.1.0"
    requires_holix = ">=0.1.21"
    permissions = frozenset({"tools", "middleware"})

    def default_settings(self) -> dict[str, Any]:
        return {"enabled": True}

    def register_tools(self, registry: Any, agent: Any) -> None:
        if self.settings.get("enabled") is False:
            return
        registry.register(HelloEchoTool())

    def register_slash_commands(self, commands: list[SlashCommandSpec]) -> None:
        commands.append(SlashCommandSpec(command="/hello", description="Hello extension demo"))

    def augment_system_prompt(self, profile: str) -> str | None:
        return "## hello extension\nTool `hello_echo` is available for demo/echo requests."

    def register_middleware(self, chain: Any, agent: Any) -> None:
        class HelloMw:
            name = "hello_mw"
            async def process(self, ctx, call_next):
                return await call_next()
        chain.add(HelloMw())


def get_agent_extension() -> HelloAgentExtension:
    return HelloAgentExtension()
```

### Install & check

```bash
pip install -e .
holix extensions agent-list
holix extensions settings hello
holix chat-command -p default
```

Settings file:

```text
~/.holix/profiles/<profile>/extension_settings/hello.yaml
```

---

## Tutorial: host extension (CLI + HTTP)

```toml
[project.entry-points."holix.extensions"]
hello_host = "hello_holix_ext.extension:get_extension"
```

```python
# hello_holix_ext/extension.py
from __future__ import annotations
from typing import Any
import typer
from holix_sdk import CAPABILITY_CLI, CAPABILITY_HTTP, ExtensionBase

cli_app = typer.Typer(help="Hello host extension")

@cli_app.command("ping")
def ping() -> None:
    typer.echo("pong from hello_host")


class HelloHostExtension(ExtensionBase):
    name = "hello_host"
    version = "0.1.0"
    requires_holix = ">=0.1.21"
    capabilities = frozenset({CAPABILITY_CLI, CAPABILITY_HTTP})
    permissions = frozenset({"gateway", "network"})

    def register_cli(self, root: typer.Typer) -> None:
        root.add_typer(cli_app, name="hello")

    def mount_gateway(self, app: Any) -> None:
        # Import FastAPI Request at module scope if you need request bodies.
        from fastapi import APIRouter
        router = APIRouter(prefix="/api/holix/hello", tags=["hello"])

        @router.get("/health")
        def health() -> dict[str, str]:
            return {"status": "ok", "extension": "hello_host"}

        app.include_router(router)


def get_extension() -> HelloHostExtension:
    return HelloHostExtension()
```

```bash
holix hello ping
curl -s http://127.0.0.1:8000/api/holix/hello/health
```

---

## Sidecar UI

```python
from holix_sdk import CAPABILITY_SIDECAR, ExtensionBase

class BillingConsoleExt(ExtensionBase):
    name = "billing_console"
    capabilities = frozenset({CAPABILITY_SIDECAR})
    permissions = frozenset({"network", "gateway"})

    def sidecar_spec(self, profile: str) -> dict | None:
        return {
            "id": "billing_console",
            "label": "Billing Console",
            "host": "127.0.0.1",
            "port": 8091,
            "argv": ["-m", "holix_billing_console.main", "--profile", profile],
        }
```

Supervisor records sidecars in gateway `state.json` and stops them on shutdown.  
Production example: **holix-billing-console** on port `8091`.

---

## Telegram plugins

| Hook | API |
|------|-----|
| Bot menu command | `api.add_command("pay", "Pay")` |
| Handlers | `api.add_handlers(registrar)` |
| Pre-agent gate | `api.add_message_gate(async_fn)` |
| Skip admin queue | `api.add_access_check(fn)` |
| Payment webhooks | host `mount_gateway` |

```toml
[project.entry-points."holix.extensions"]
telegram_billing = "holix_telegram_billing.extension:get_extension"
[project.entry-points."holix.telegram.extensions"]
telegram_billing = "holix_telegram_billing.extension:get_extension"
```

Config is **env-only** (`HOLIX_BILLING_*`). When billing is enabled, users auto-onboard on free quota — **no admin approval queue**.

Reference: **holix-telegram-billing**.

---

## MAX plugins

| Hook | API |
|------|-----|
| Command | `api.add_command` + `api.add_command_handler` |
| Gate | `api.add_message_gate` |
| Callbacks | `api.add_callback_handler` |
| Webhook | `POST /api/holix/max-billing/webhook/yookassa` |

Env: `HOLIX_MAX_BILLING_*` (falls back to shared YooKassa keys).  
No native Stars on MAX — typically YooKassa redirect + webhook.

Reference: **holix-max-billing**.

---

## LLM middleware

On agent init Holix:

1. Discover agent extensions (packages + drop-ins)
2. Load settings
3. Register tools / slash / prompt
4. `register_middleware(chain, agent)`
5. Proxy `agent.client.chat.completions.create`

```python
class MyMw:
    name = "my_mw"
    async def process(self, ctx, call_next):
        result = await call_next()
        return result
```

Reference: `packages/holix-extension-demo`.

---

## Host lifecycle hooks

| Hook | When |
|------|------|
| `on_startup(ctx)` | Once per process |
| `register_cli(app)` | CLI assembly |
| `mount_gateway(app)` | Gateway boot |
| `register_telegram(api)` | Telegram bot build |
| `register_max(api)` | MAX bot build |
| `sidecar_spec(profile)` | Sidecar start |
| `on_shutdown()` | Process stop |

Factories must return an **instance**:

```python
def get_extension():
    return MyExtension()
```

---

## Gateway contract (summary)

Base URL: `http://127.0.0.1:8000`

| Header | Value |
|--------|-------|
| `Authorization` | `Bearer hx_…` |
| `X-API-Key` | `hx_…` |

| Extension | Prefix |
|-----------|--------|
| telegram_billing | `/api/holix/billing/*` |
| max_billing | `/api/holix/max-billing/*` |
| studio | `/studio` |
| yours | e.g. `/api/holix/hello` |

OpenAPI: `/openapi.json`, Swagger: `/docs`. Full list: [GATEWAY_API.md](GATEWAY_API.md).

---

## Ecosystem packages

| Package | Kind | Role |
|---------|------|------|
| `holix-extension-demo` | agent | `demo_echo`, `/demo`, LLM stats |
| `holix-telegram-billing` | host + TG | plans, Stars, YooKassa, gate |
| `holix-max-billing` | host + MAX | plans, YooKassa, gate |
| `holix-billing-console` | sidecar | admin UI (~8091) |
| `holix-studio` | host | SDD Studio UI |

```bash
ln -s /opt/holix-extensions/holix-telegram-billing \
      /var/lib/holix/extensions/holix-telegram-billing
```

---

## CLI cheat sheet

```bash
holix extensions list
holix extensions agent-list
holix extensions list --json
holix extensions settings <name>
holix extensions settings <name> --set key=value
holix doctor
holix gateway start -f
```

---

## Release checklist

- [ ] Host imports only `holix_sdk`
- [ ] Factories return instances
- [ ] `name`, `version`, `requires_holix`, `permissions`, `capabilities` set
- [ ] `holix.plugin.json` present
- [ ] Visible in `holix extensions list` / `agent-list`
- [ ] Tools / slash / health verified
- [ ] Webhook handlers: `Request` at module scope
- [ ] Tests pass
- [ ] LICENSE included

```bash
uv build && uv publish
pip install my-holix-extension
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Missing from `list` | Entry point / install path / typo |
| Tool not in agent | `tools` permission; agent entry; settings `enabled` |
| Health empty providers | Shared host instance; env load; billing disabled in tariffs |
| Webhook 422 `query request` | Module-level FastAPI `Request` import |
| Messenger asks admin approval | Billing disabled → `ACCESS_REQUESTS` queue |
| Sidecar not starting | Missing capability / `sidecar_spec` None / port busy |

---

## External apps without Python

1. `holix gateway start`
2. Profile API key
3. Use [GATEWAY_API.md](GATEWAY_API.md)

---

## Licensing

| Component | License |
|-----------|---------|
| Holix core | MIT |
| holix-sdk | MIT |
| Your open extension | Your choice (MIT recommended) |
| Proprietary products | Separate license |

---

## Next steps

1. Copy the `hello-holix-ext` example or `packages/holix-extension-demo`
2. `pip install -e .` → `holix extensions agent-list`
3. Add the tool / HTTP / messenger hook you need
4. Production: env, nginx webhooks, `holix doctor`

See also: [Architecture](ARCHITECTURE.md) · [Security](SECURITY.md) · [Deployment](DEPLOYMENT.md)
