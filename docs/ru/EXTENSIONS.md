# Расширения Holix — руководство автора

> **Версия API SDK:** `holix_sdk.__api_version__ == 1`

Это руководство описывает, как создавать расширения Holix с пакетом **`holix-sdk`** — **отдельным устанавливаемым Python-пакетом** со стабильным публичным API. Авторы расширений должны зависеть от `holix-sdk`, а не от внутренних модулей `core.*` и `cli.*`.

См. также:

- [BUILD_WITHOUT_HOLIX.md](../en/BUILD_WITHOUT_HOLIX.md) — внешние приложения через HTTP/MCP (без import Holix)
- [EXTENSION_GATEWAY.md](../en/EXTENSION_GATEWAY.md) — контракт gateway для host-расширений
- [GATEWAY_API.md](GATEWAY_API.md) — полный справочник HTTP API

---

## Архитектура

```
┌─────────────────────────────────────────────────────────┐
│  Ядро Holix (MIT) — агент, CLI, gateway, загрузчик      │
└───────────────────────────┬─────────────────────────────┘
                            │
              ┌─────────────▼─────────────┐
              │   holix-sdk (MIT, PyPI)    │  ← импорт ТОЛЬКО отсюда
              │   стабильный API           │
              └─────────────┬───────────────┘
                            │
     ┌──────────────────────┼──────────────────────┐
     │                      │                      │
holix.extensions    holix.agent.extensions    HTTP / MCP
(host: CLI, HTTP)   (tools, slash, prompts)   (любой язык)
```

| Паттерн | Группа entry points | Типичное применение |
|---------|---------------------|---------------------|
| **Host-расширение** | `holix.extensions` | CLI-команды, FastAPI-роуты, sidecar UI |
| **Agent-расширение** | `holix.agent.extensions` | Tools, slash-команды, фрагменты промпта |
| **Внешнее приложение** | — | Mobile, web, SaaS через Gateway API |

Встроенные host-расширения в ядре: `telegram`, `max`.  
Эталон agent-расширения в репозитории Holix: `packages/holix-extension-demo`.  
Эталон host-расширения (отдельный репозиторий): [holix-studio](https://github.com/javded-itres/holix-studio).

---

## holix-sdk — отдельный пакет

`holix-sdk` находится в `packages/holix-sdk/` репозитория Holix и публикуется **независимо** от ядра.

### Установка

```bash
# Пользователи и авторы расширений
pip install holix-sdk Holix

# Разработчики монорепо Holix
uv sync --extra sdk
```

### Зачем отдельный пакет?

1. **Стабильный контракт** — breaking changes только в major-версиях `holix-sdk`.
2. **Чёткая граница** — host/UI код не импортирует `core.*` и `cli.*`.
3. **Независимый релиз** — авторы пинят `holix-sdk>=0.1.0` без форка Holix.
4. **Лицензия** — `holix-sdk` под MIT, как и ядро.

### Публичные модули

| Модуль | Импорт | Назначение |
|--------|--------|------------|
| `holix_sdk` | `HolixExtension`, `ExtensionBase`, `ExtensionContext`, `CAPABILITY_*` | Протокол host-расширения |
| `holix_sdk.agent` | `AgentExtensionBase`, `SlashCommandSpec` | Протокол agent-расширения |
| `holix_sdk.host` | `AgentCommands`, `all_slash_commands`, … | Мост host UI → агент |
| `holix_sdk.i18n` | `LocaleStore`, `t`, `host_locale` | Локализация |
| `holix_sdk.models` | `ModelChoice`, `build_models_menu`, … | Выбор модели в runtime |
| `holix_sdk.profile` | `ProfileManager`, `init_profile` | Работа с профилями |
| `holix_sdk.agent_runtime` | `HolixAgent`, события агента | Жизненный цикл и события |
| `holix_sdk.security` | confirmation, web security | Подтверждения и токены |
| `holix_sdk.commands` | `command_specs` | Меню команд host |
| `holix_sdk.paths` | `realpath_under`, … | Безопасные пути |

Проверка версии API:

```python
from holix_sdk import __api_version__
assert __api_version__ == 1
```

---

## Создание нового расширения — по шагам

### 1. Выберите тип

| Задача | Тип | Entry point |
|--------|-----|-------------|
| Команда `holix mycmd` | Host | `holix.extensions` |
| Роуты на gateway `:8000` | Host | `holix.extensions` |
| Tool для агента | Agent | `holix.agent.extensions` |
| Slash `/mycommand` | Agent | `holix.agent.extensions` |
| Текст в system prompt | Agent | `holix.agent.extensions` |

Один Python-пакет может регистрировать **оба** entry point.

### 2. Структура проекта

```
my-holix-extension/
├── pyproject.toml
├── README.md
├── LICENSE
├── my_holix_ext/
│   ├── __init__.py
│   ├── holix.plugin.json      # опциональный manifest
│   ├── extension.py           # host (holix.extensions)
│   ├── agent.py               # agent (holix.agent.extensions)
│   └── tools.py               # tools (если нужны)
└── tests/
    └── test_extension.py
```

### 3. `pyproject.toml`

**Только agent-расширение:**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "my-holix-extension"
version = "0.1.0"
description = "Моё расширение Holix"
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

**Host-расширение** — добавьте:

```toml
[project.entry-points."holix.extensions"]
myext = "my_holix_ext.extension:get_extension"
```

**FastAPI** (если нужны HTTP-роуты):

```toml
dependencies = [
    "Holix>=0.1.21",
    "holix-sdk>=0.1.0",
    "fastapi>=0.136.0",
]
```

### 4. `holix.plugin.json` (опционально)

Файл внутри пакета Python (например `my_holix_ext/holix.plugin.json`):

```json
{
  "id": "myext",
  "version": "0.1.0",
  "requires": { "holix": ">=0.1.21", "holix_sdk": ">=0.1.0" },
  "description": "Краткое описание",
  "capabilities": ["agent"],
  "permissions": ["tools"]
}
```

Capabilities: `cli`, `http`, `sidecar`, `agent`.  
Holix подставляет поля из manifest, если в классе расширения оставлены значения по умолчанию.

**Sidecar (отдельный порт вместе с gateway):** host-расширение с capability `sidecar` реализует `sidecar_spec(profile) → dict | None` (`id`, `host`, `port`, `argv`, опционально `env`, `label`). Supervisor поднимает процесс при `holix gateway start` и останавливает при shutdown. Пример: `holix-billing-console`.

### 5. Agent-расширение

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
        commands.append(SlashCommandSpec("/myext", "Моя slash-команда"))

    def augment_system_prompt(self, profile: str) -> str | None:
        return "## Моё расширение\nДополнительные инструкции для агента."


def get_agent_extension() -> MyAgentExtension:
    return MyAgentExtension()
```

**Tool** (`core.tools.base.BaseTool` разрешён только в agent-расширениях):

```python
# my_holix_ext/tools.py
from __future__ import annotations

from typing import Any

from core.tools.base import BaseTool


class MyTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "my_tool"
        self.description = "Делает что-то полезное."
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }

    async def execute(self, query: str, **kwargs: Any) -> str:
        return f"Результат: {query}"
```

### 6. Host-расширение

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
    description = "Моё host-расширение"
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

**Правила для host-кода:**

- Импортируйте **`holix_sdk`** для протоколов, host bridge, i18n, models.
- **Не** импортируйте `core.*`, `cli.*`, `integrations.*` (кроме `core.tools.base` — только для agent).
- FastAPI / Typer — в **вашем** пакете.

### 7. Установка и проверка

```bash
# Разработка (editable)
pip install -e ./my-holix-extension

# Проверка обнаружения
holix extensions list
holix extensions agent-list
holix extensions list --json
```

Запустите агента и убедитесь, что tool зарегистрирован:

```bash
holix chat-command -p default
```

### 8. Тесты

```python
# tests/test_extension.py
from my_holix_ext.agent import get_agent_extension


def test_agent_extension_metadata() -> None:
    ext = get_agent_extension()
    assert ext.name == "myext"
    assert "tools" in ext.permissions
```

Запуск: `pytest tests/ -q`

---

## Разрешения (permissions)

Указывайте только необходимое в `permissions` (код или manifest):

| Permission | Нужен для |
|------------|-----------|
| `tools` | Регистрация agent tools |
| `gateway` | `mount_gateway()` — роуты на gateway Holix |
| `network` | Исходящий HTTP, мессенджеры, sidecar |
| `filesystem` | Файловые API workspace в host |
| `subprocess` | Запуск дочерних процессов |

При недостатке permissions Holix пишет предупреждение в лог и **пропускает** регистрацию.

---

## CLI

```bash
holix extensions list           # host-расширения
holix extensions agent-list     # agent-расширения
holix extensions list --json    # JSON для автоматизации
```

---

## Публикация

### `holix-sdk` (для мейнтейнеров)

Из каталога `packages/holix-sdk/`:

```bash
uv build
uv publish
```

Имя на PyPI: **`holix-sdk`**.

### Ваше расширение

1. Укажите `name`, `version`, `dependencies` в `pyproject.toml`.
2. Зафиксируйте `holix-sdk>=0.1.0` и `Holix>=0.1.21`.
3. `uv build && uv publish`.
4. Пользователи: `pip install my-holix-extension`.

После `pip install` Holix находит расширение через entry points — **изменения в ядре не нужны**.

---

## Чеклист перед релизом

- [ ] Host-код импортирует только `holix_sdk` (не `core` / `cli`)
- [ ] Factory-функции возвращают экземпляры (`get_extension()`, `get_agent_extension()`)
- [ ] Заданы `name`, `version`, `requires_holix`, `permissions`
- [ ] Есть `holix.plugin.json` (рекомендуется)
- [ ] `holix extensions list` / `agent-list` показывает пакет
- [ ] Тесты проходят
- [ ] Файл LICENSE (MIT для открытых расширений)

---

## Лицензирование

| Компонент | Лицензия |
|-----------|----------|
| Ядро Holix | MIT |
| holix-sdk | MIT |
| Ваше MIT-расширение | На ваш выбор (рекомендуется MIT) |
| Проприетарные продукты (Holix Studio) | Отдельная лицензия |

См. [THIRD_PARTY_LICENSES.md](../../THIRD_PARTY_LICENSES.md).