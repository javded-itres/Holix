# Расширения Holix

> **SDK API:** `holix_sdk.__api_version__ == 1`  
> Расширения — основной способ добавлять tools, slash-команды, HTTP API, UI и плагины мессенджеров **без форка ядра**.

На этой странице: архитектура, типы расширений, permissions, установка, пошаговое создание с **рабочими примерами**, drop-in, sidecar, Telegram/MAX, middleware, CLI и чеклист релиза.

Связанные разделы: [MCP](MCP.md) · [API Gateway](GATEWAY.md) · [Справочник API](GATEWAY_API.md) · [Telegram](TELEGRAM.md) · [MAX](MAX.md) · [CLI](CLI.md)

---

## Зачем нужны расширения

| Задача | Как решать расширением |
|--------|------------------------|
| Новый tool для агента | Agent-расширение + `BaseTool` |
| Slash `/mycommand` в TUI/агенте | Agent-расширение |
| Команда `holix mycmd` | Host-расширение (`register_cli`) |
| HTTP-эндпоинты на gateway `:8000` | Host-расширение (`mount_gateway`) |
| Отдельный UI на другом порту | Host + capability `sidecar` |
| Биллинг / paywall в Telegram или MAX | Host + `register_telegram` / `register_max` |
| Статистика каждого LLM-вызова | Agent + `register_middleware` |
| Внешний SaaS/mobile | Без Python — [Gateway API](GATEWAY_API.md) |

**Принцип:** ядро Holix остаётся MIT-ядром агента; продукты (Studio, billing, кастомные tools) живут в отдельных пакетах и подключаются через entry points или папку профиля.

---

## Архитектура

```
┌──────────────────────────────────────────────────────────────┐
│  Ядро Holix (MIT) — agent, CLI, gateway, загрузчик расширений │
└──────────────────────────────┬───────────────────────────────┘
                               │
                 ┌─────────────▼─────────────┐
                 │  holix-sdk (MIT, PyPI)     │  ← импорт ТОЛЬКО отсюда (host)
                 │  стабильный публичный API  │
                 └─────────────┬─────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
 holix.extensions      holix.agent.extensions     HTTP / MCP
 (CLI, gateway,        (tools, slash, prompts,   (любой язык,
  sidecar, TG/MAX)      middleware, settings)      без import Holix)
```

| Паттерн | Entry point / способ | Что даёт |
|---------|----------------------|----------|
| **Host** | `holix.extensions` | CLI, FastAPI-роуты, sidecar, `register_telegram` / `register_max` |
| **Agent** | `holix.agent.extensions` | Tools, slash, system prompt, LLM middleware, settings |
| **Drop-in** | папка `~/.holix/profiles/<p>/extensions/<name>/` | То же без `pip install`; удалили папку — выгрузилось |
| **Telegram plugin** | `holix.telegram.extensions` **или** host `register_telegram` | Команды бота, handlers, message gate, access check |
| **MAX plugin** | `holix.max.extensions` **или** host `register_max` | Аналогично для MAX |
| **Внешнее приложение** | Bearer API key | Мобильные/web/SaaS через gateway |

В ядре: host-расширения `telegram`, `max`.  
Эталон agent: `packages/holix-extension-demo` в репозитории Holix.  
Эталон host UI: [holix-studio](https://github.com/javded-itres/holix-studio).  
Эталон биллинга: `holix-telegram-billing`, `holix-max-billing`, `holix-billing-console`.

---

## Возможности (capabilities)

Объявляйте в классе расширения или в `holix.plugin.json`:

| Capability | Константа SDK | Назначение |
|------------|---------------|------------|
| `cli` | `CAPABILITY_CLI` | Подкоманды Typer (`holix <name> …`) |
| `http` | `CAPABILITY_HTTP` | Роуты на Holix gateway (`mount_gateway`) |
| `sidecar` | `CAPABILITY_SIDECAR` | Отдельный процесс/порт при `holix gateway start` |
| `agent` | — (agent entry) | Tools / slash / prompt / middleware |

Один пакет может иметь **и** host, **и** agent entry points.

---

## Разрешения (permissions)

Указывайте **минимум** необходимого. При нехватке Holix пишет warning и **пропускает** регистрацию.

| Permission | Нужен для |
|------------|-----------|
| `tools` | Регистрация agent tools |
| `middleware` | LLM middleware chain |
| `gateway` | `mount_gateway()` |
| `network` | Исходящий HTTP, мессенджеры, sidecar |
| `filesystem` | Файловые API workspace (host) |
| `subprocess` | Дочерние процессы |

---

## holix-sdk

Отдельный пакет (`packages/holix-sdk/`, PyPI: **`holix-sdk`**). Host-код **не** должен импортировать `core.*` / `cli.*`.

```bash
pip install holix-sdk Holix
# в monorepo Holix:
uv sync --extra sdk
```

| Модуль | Назначение |
|--------|------------|
| `holix_sdk` | `ExtensionBase`, `ExtensionContext`, `CAPABILITY_*` |
| `holix_sdk.agent` | `AgentExtensionBase`, `SlashCommandSpec` |
| `holix_sdk.host` | Мост host UI → агент |
| `holix_sdk.i18n` | Локализация |
| `holix_sdk.models` | Выбор модели |
| `holix_sdk.profile` | Профили |
| `holix_sdk.agent_runtime` | Жизненный цикл агента |
| `holix_sdk.security` | Подтверждения, токены |
| `holix_sdk.paths` | Безопасные пути |

```python
from holix_sdk import __api_version__
assert __api_version__ == 1
```

**Исключение:** внутри **agent**-расширений разрешён `core.tools.base.BaseTool` и (рекомендуется) `core.extensions.agent_base.AgentExtensionBase` для settings + middleware.

---

## Как подключить готовое расширение

### 1. Через pip / uv (entry points)

```bash
pip install my-holix-extension
# или editable при разработке:
pip install -e ./my-holix-extension

holix extensions list          # host
holix extensions agent-list    # agent
holix extensions list --json
```

После установки Holix находит пакет **автоматически** — править ядро не нужно.

### 2. Drop-in в профиль (без pip)

```text
~/.holix/profiles/default/extensions/my_stats/
  agent.py                 # def get_agent_extension()
  settings.default.yaml    # опционально
  holix.plugin.json        # опционально
  extension.py             # host: def get_extension() / get_host_extension()
```

Также: `~/.holix/extensions/<name>/` (глобально) и симлинки в production (как на VDS: `/var/lib/holix/extensions/…`).

Удалили папку → при следующем старте gateway/агента расширения нет.

### 3. Переменные окружения продукта

Многие host-продукты (billing) конфигурируются **только env** профиля:

```bash
# profiles/production/.env
HOLIX_BILLING_ENABLED=true
HOLIX_BILLING_PROVIDERS=stars,yookassa
HOLIX_MAX_BILLING_ENABLED=true
```

См. README пакетов `holix-telegram-billing` / `holix-max-billing`.

### 4. Проверка

```bash
holix extensions list
holix extensions agent-list
holix extensions settings demo          # settings agent-расширения
holix doctor
holix gateway start -f
# OpenAPI: http://127.0.0.1:8000/docs
```

---

## Пошагово: создать agent-расширение (полный пример)

### Структура

```text
hello-holix-ext/
├── pyproject.toml
├── README.md
├── hello_holix_ext/
│   ├── __init__.py
│   ├── holix.plugin.json
│   ├── agent.py
│   └── tools.py
└── tests/
    └── test_extension.py
```

### `pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "hello-holix-ext"
version = "0.1.0"
description = "Пример agent-расширения Holix"
readme = "README.md"
license = "MIT"
requires-python = ">=3.12"
dependencies = [
    "Holix>=0.1.21",
    "holix-sdk>=0.1.0",
]

[project.entry-points."holix.agent.extensions"]
hello = "hello_holix_ext.agent:get_agent_extension"

[tool.hatch.build.targets.wheel]
packages = ["hello_holix_ext"]
```

### `holix.plugin.json`

```json
{
  "id": "hello",
  "version": "0.1.0",
  "requires": { "holix": ">=0.1.21", "holix_sdk": ">=0.1.0" },
  "description": "Echo tool + slash /hello",
  "capabilities": ["agent"],
  "permissions": ["tools", "middleware"]
}
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
        self.description = "Эхо-инструмент демо-расширения. Повторяет строку."
        self.risk_level = "no"  # no | low | medium | high
        self.parameters = {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Текст для эхо"},
            },
            "required": ["text"],
        }

    async def execute(self, text: str = "", **kwargs: Any) -> str:
        return f"👋 hello_echo: {text}"
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
        return {"enabled": True, "prefix": "👋"}

    def register_tools(self, registry: Any, agent: Any) -> None:
        if self.settings.get("enabled") is False:
            return
        registry.register(HelloEchoTool())

    def register_slash_commands(self, commands: list[SlashCommandSpec]) -> None:
        commands.append(
            SlashCommandSpec(command="/hello", description="Демо slash расширения hello")
        )

    def augment_system_prompt(self, profile: str) -> str | None:
        return (
            "## Расширение hello\n"
            "Доступен tool `hello_echo`. Используй его, когда пользователь просит echo/демо."
        )

    def register_middleware(self, chain: Any, agent: Any) -> None:
        """Каждый LLM-вызов проходит через onion middleware."""

        class HelloMw:
            name = "hello_mw"

            async def process(self, ctx, call_next):
                # ctx.model, ctx.messages, ctx.duration_ms, ctx.response, …
                return await call_next()

        chain.add(HelloMw())


def get_agent_extension() -> HelloAgentExtension:
    return HelloAgentExtension()
```

### Установка и проверка

```bash
cd hello-holix-ext
pip install -e .

holix extensions agent-list
# → hello 0.1.0 …

# Настройки (файл создаётся из default_settings):
holix extensions settings hello
holix extensions settings hello --set enabled=true

# Чат: агент должен видеть tool hello_echo
holix chat-command -p default
```

Settings хранятся в:

```text
~/.holix/profiles/<profile>/extension_settings/hello.yaml
```

или в `config.yaml`:

```yaml
extension_settings:
  hello:
    enabled: true
    prefix: "👋"
```

### Минимальный тест

```python
# tests/test_extension.py
from hello_holix_ext.agent import get_agent_extension

def test_meta():
    ext = get_agent_extension()
    assert ext.name == "hello"
    assert "tools" in ext.permissions
```

```bash
pytest tests/ -q
```

---

## Пошагово: host-расширение (CLI + HTTP)

### Entry points

```toml
[project.entry-points."holix.extensions"]
hello_host = "hello_holix_ext.extension:get_extension"
```

### Код

```python
# hello_holix_ext/extension.py
from __future__ import annotations
from typing import Any
import typer
from holix_sdk import CAPABILITY_CLI, CAPABILITY_HTTP, ExtensionBase

cli_app = typer.Typer(help="Hello host extension")

@cli_app.command("ping")
def ping() -> None:
    """Проверка, что host-расширение загружено."""
    typer.echo("pong from hello_host")


class HelloHostExtension(ExtensionBase):
    name = "hello_host"
    version = "0.1.0"
    requires_holix = ">=0.1.21"
    description = "CLI + HTTP demo"
    capabilities = frozenset({CAPABILITY_CLI, CAPABILITY_HTTP})
    permissions = frozenset({"gateway", "network"})

    def register_cli(self, root: typer.Typer) -> None:
        root.add_typer(cli_app, name="hello")

    def mount_gateway(self, app: Any) -> None:
        # Важно: импорт FastAPI Request — на уровне модуля (не внутри nested fn),
        # иначе FastAPI 0.13x может трактовать request как query → 422.
        from fastapi import APIRouter

        router = APIRouter(prefix="/api/holix/hello", tags=["hello"])

        @router.get("/health")
        def health() -> dict[str, str]:
            return {"status": "ok", "extension": "hello_host"}

        app.include_router(router)


def get_extension() -> HelloHostExtension:
    return HelloHostExtension()
```

### Проверка

```bash
pip install -e .
holix extensions list
holix hello ping
# → pong from hello_host

holix gateway start -f
curl -s http://127.0.0.1:8000/api/holix/hello/health
# → {"status":"ok","extension":"hello_host"}
```

---

## Sidecar (отдельный UI-порт)

Host-расширение с capability `sidecar` поднимает companion-процесс вместе с gateway.

```python
from holix_sdk import CAPABILITY_SIDECAR, ExtensionBase

class BillingConsoleExt(ExtensionBase):
    name = "billing_console"
    capabilities = frozenset({CAPABILITY_SIDECAR})
    permissions = frozenset({"network", "gateway"})

    def should_start_sidecar(self, profile: str) -> bool:
        return True

    def sidecar_spec(self, profile: str) -> dict | None:
        return {
            "id": "billing_console",
            "label": "Billing Console",
            "host": "127.0.0.1",
            "port": 8091,
            "url_path": "/",
            "argv": ["-m", "holix_billing_console.main", "--profile", profile],
            # для drop-in часто нужен PYTHONPATH на корень пакета
            "env": {},
        }
```

Supervisor пишет sidecars в `state.json` gateway и гасит процессы при stop.  
Пример в проде: **holix-billing-console** (`http://127.0.0.1:8091`).

---

## Плагины Telegram

Биллинг и paywall **не** в ядре — только в расширениях.

| Hook | API |
|------|-----|
| Команда в меню бота | `api.add_command("pay", "Оплата")` |
| Handlers (aiogram) | `api.add_handlers(registrar)` |
| Gate до агента | `api.add_message_gate(async_fn)` |
| Auto-access без админа | `api.add_access_check(fn)` |
| Webhook оплаты | host `mount_gateway` → `POST /api/holix/billing/webhook/…` |

```toml
[project.entry-points."holix.extensions"]
telegram_billing = "holix_telegram_billing.extension:get_extension"

[project.entry-points."holix.telegram.extensions"]
telegram_billing = "holix_telegram_billing.extension:get_extension"
```

```python
class TelegramBillingExtension:
    name = "telegram_billing"
    version = "0.4.2"
    capabilities = frozenset({"http", "cli"})
    permissions = frozenset({"network", "gateway", "tools"})

    def register_telegram(self, api):
        api.add_command("pay", "Оформить подписку")
        api.add_command("tariffs", "Тарифы")
        api.add_handlers(lambda a: register_billing_handlers(a, self._service))
        api.add_message_gate(make_message_gate(self._service))
        api.add_access_check(make_access_check(self._service, api.bot_profile))

    def mount_gateway(self, app):
        # GET  /api/holix/billing/health
        # POST /api/holix/billing/webhook/yookassa
        ...

def get_extension():
    return TelegramBillingExtension()
```

**Конфиг только через env** (`HOLIX_BILLING_*`), не через YAML Holix:

```env
HOLIX_BILLING_ENABLED=true
HOLIX_BILLING_FREE_MESSAGES_PER_MONTH=50
HOLIX_BILLING_PROVIDERS=stars,yookassa
HOLIX_BILLING_YOOKASSA_SHOP_ID=...
HOLIX_BILLING_YOOKASSA_SECRET_KEY=...
HOLIX_BILLING_PUBLIC_BASE_URL=https://messengers.example.com
```

Когда billing **включён**, пользователи onboarding-ятся автоматически (free-квота) — **без** очереди одобрения админа.  
Команды: `/tariffs`, `/pay`, `/topup`, `/subscription`, `/promo`.

Референс: репозиторий **holix-telegram-billing**.

---

## Плагины MAX

Тот же контракт, другой messenger API.

| Hook | API |
|------|-----|
| Команда | `api.add_command` + `api.add_command_handler` |
| Gate | `api.add_message_gate` |
| Inline/callback | `api.add_callback_handler` |
| Webhook | `POST /api/holix/max-billing/webhook/yookassa` |

```toml
[project.entry-points."holix.max.extensions"]
max_billing = "holix_max_billing.extension:get_extension"
```

Env: `HOLIX_MAX_BILLING_*` (fallback на `HOLIX_BILLING_YOOKASSA_*` / планы).  
Нативной оплаты Stars в MAX нет — обычно **ЮKassa** (redirect + webhook).

Референс: **holix-max-billing**.

---

## LLM middleware (onion)

При инициализации агента Holix:

1. Discover agent-расширений (pip + drop-in)
2. Загрузка settings (`default_settings` → config → yaml settings)
3. `register_tools` / slash / prompt
4. `register_middleware(chain, agent)`
5. Proxy на `agent.client.chat.completions.create`

Каждый middleware:

```python
class MyMw:
    name = "my_mw"

    async def process(self, ctx, call_next):
        # до LLM
        result = await call_next()
        # после LLM: ctx.response, ctx.duration_ms, …
        return result
```

Удалили пакет/папку → при следующем старте middleware и tools исчезают.

Эталон: `packages/holix-extension-demo` (`RequestStatsMiddleware` пишет jsonl).

---

## Drop-in: быстрый stats без pip

```text
~/.holix/profiles/default/extensions/request_stats/agent.py
```

```python
from __future__ import annotations
from typing import Any
from holix_sdk.agent import SlashCommandSpec

try:
    from core.extensions.agent_base import AgentExtensionBase
except ImportError:
    from holix_sdk.agent import AgentExtensionBase


class StatsExt(AgentExtensionBase):
    name = "request_stats"
    version = "0.0.1"
    permissions = frozenset({"middleware"})

    def default_settings(self) -> dict[str, Any]:
        return {"enabled": True}

    def register_middleware(self, chain: Any, agent: Any) -> None:
        if not self.settings.get("enabled", True):
            return

        class CountMw:
            name = "request_stats"
            def __init__(self):
                self.n = 0
            async def process(self, ctx, call_next):
                self.n += 1
                return await call_next()

        chain.add(CountMw())


def get_agent_extension():
    return StatsExt()
```

```bash
holix extensions agent-list
# request_stats …
```

---

## Жизненный цикл host-расширения

| Hook | Когда |
|------|--------|
| `on_startup(ctx)` | Один раз на процесс (gateway / CLI) |
| `register_cli(app)` | Сборка CLI `holix` |
| `mount_gateway(app)` | Старт FastAPI gateway |
| `register_telegram(api)` | Сборка Telegram-бота |
| `register_max(api)` | Сборка MAX-бота |
| `sidecar_spec(profile)` | Supervisor поднимает sidecar |
| `on_shutdown()` | Остановка процесса |

**Важно:** Holix должен вызывать `mount_gateway` на **тех же экземплярах**, что и `on_startup` (stateful-сервисы, billing `_service`). Иначе health/webhook «пустые».

Factory **обязан** возвращать **экземпляр**:

```python
def get_extension():
    return MyExtension()   # не класс!
```

---

## Контракт gateway для расширений

Базовый URL: `http://127.0.0.1:8000` (из profile `.env`).

Аутентификация (management API):

| Header | Значение |
|--------|----------|
| `Authorization` | `Bearer hx_…` |
| `X-API-Key` | `hx_…` |

Примеры mount-префиксов:

| Расширение | Prefix | Условие |
|------------|--------|---------|
| telegram (core) | `/api/holix/profiles/{id}/telegram` | профиль |
| max (core) | `/api/holix/…/max` | webhook env |
| telegram_billing | `/api/holix/billing/*` | extension loaded |
| max_billing | `/api/holix/max-billing/*` | extension loaded |
| studio | `/studio` | `HOLIX_STUDIO_ENABLED=1` |
| ваше | любой, напр. `/api/holix/hello` | ваш `include_router` |

Живая схема: `GET /openapi.json`, UI: `GET /docs`.  
Полный список: [GATEWAY_API.md](GATEWAY_API.md).

---

## Реальные пакеты экосистемы

| Пакет | Тип | Что делает |
|-------|-----|------------|
| `holix-extension-demo` | agent | tool `demo_echo`, `/demo`, LLM stats middleware |
| `holix-telegram-billing` | host + TG | тарифы, Stars, ЮKassa, gate, auto-access |
| `holix-max-billing` | host + MAX | тарифы, ЮKassa, gate |
| `holix-billing-console` | host sidecar | админ-UI подписчиков/тарифов (~8091) |
| `holix-studio` | host | SDD Studio UI |

Установка drop-in на сервере (пример):

```bash
ln -s /opt/holix-extensions/holix-telegram-billing \
      /var/lib/holix/extensions/holix-telegram-billing
systemctl restart holix-gateway@production
```

---

## CLI-шпаргалка

```bash
holix extensions list
holix extensions agent-list
holix extensions list --json
holix extensions settings <name>
holix extensions settings <name> --set key=value

holix doctor
holix gateway start -f --host 127.0.0.1
```

---

## Чеклист перед релизом

- [ ] Host импортирует только `holix_sdk` (не `core` / `cli` / `integrations`)
- [ ] Factory: `get_extension()` / `get_agent_extension()` возвращают **instance**
- [ ] Заданы `name`, `version`, `requires_holix`, `permissions`, `capabilities`
- [ ] Есть `holix.plugin.json` (рекомендуется)
- [ ] `holix extensions list` / `agent-list` видит пакет
- [ ] Tools / slash / health-роуты проверены вручную
- [ ] Для webhook: `Request` импортирован на уровне модуля (не nested)
- [ ] Тесты `pytest` зелёные
- [ ] LICENSE (MIT для open-source)

### Публикация

```bash
# pyproject: name, version, Holix>=0.1.21, holix-sdk>=0.1.0
uv build && uv publish
# пользователи:
pip install my-holix-extension
```

---

## Типичные проблемы

| Симптом | Причина / решение |
|---------|-------------------|
| Расширения нет в `list` | Нет entry point / не `pip install -e` / опечатка в module path |
| Tool не виден агенту | Нет permission `tools`; agent entry не загружен; settings `enabled=false` |
| Health `providers: []` | Разные instance host-расширения; env не загружен; billing disabled в tariffs.json |
| Webhook HTTP 422 `query request` | `Request` импортирован внутри nested handler — вынести в globals модуля |
| MAX/TG просит одобрение админа | Billing **выключен** (`enabled: false` в tariffs / env) → работает queue `ACCESS_REQUESTS` |
| Sidecar не стартует | Нет capability `sidecar` / `sidecar_spec` вернул `None` / порт занят |
| ImportError `core.*` в host | Host должен использовать только `holix-sdk` |

---

## Внешние приложения без Python

Не обязательно писать extension на Python. Любой язык:

1. `holix gateway start`
2. API key профиля
3. Chat/sessions/jobs через [GATEWAY_API.md](GATEWAY_API.md)

Это отдельный паттерн «внешнее приложение», не host/agent entry point.

---

## Лицензии

| Компонент | Лицензия |
|-----------|----------|
| Ядро Holix | MIT |
| holix-sdk | MIT |
| Ваше open-source расширение | на ваш выбор (рекомендуется MIT) |
| Проприетарные продукты (Studio и т.п.) | отдельная лицензия |

---

## Куда идти дальше

1. Скопируйте пример `hello-holix-ext` выше или `packages/holix-extension-demo`
2. `pip install -e .` → `holix extensions agent-list`
3. Добавьте tool / HTTP / TG-хук под свою задачу
4. Для продакшена: env, nginx webhook, `holix doctor`

См. также: [Архитектура](ARCHITECTURE.md) · [Безопасность](SECURITY.md) · [Деплой](DEPLOYMENT.md)
