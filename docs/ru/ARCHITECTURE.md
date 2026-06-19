# Архитектура

Holix — платформа AI-агента на Python: единый цикл выполнения, события для UI и подключаемые tools/skills/MCP.

## Поток выполнения

```
HolixAgent (core/agent.py)
    → run_agent_loop() / LangGraph (core/agent_execution.py)
    → события AgentEvent (core/agent_events.py)
    → ToolRegistry, MemoryManager, SkillManager
```

| Адаптер | Роль |
|---------|------|
| `AgentLoop` | Сбор событий в итоговую строку (CLI chat) |
| `StreamingAgentLoop` | SSE для API gateway |
| TUI host | Подписка на события, слэш-команды, подтверждения |

## Карта компонентов

| Компонент | Путь | Роль |
|-----------|------|------|
| Агент | `core/agent.py` | Память, навыки, tools, цикл |
| Выполнение | `core/agent_execution.py` | Единый agent loop |
| События | `core/agent_events.py` | Pub/sub `AgentEventBus` |
| Tools | `core/tools/` | `BaseTool`, registry, browser, terminal |
| Память | `core/memory/` | SQLite + ChromaDB |
| Навыки | `core/skills/` | Markdown, generator, hub |
| Модели | `core/models/` | Мульти-провайдер |
| MCP | `core/mcp/` | Клиент MCP, префикс tools |
| Hub | `core/hub/` | Каталоги, slash registry |
| Безопасность | `core/security/` | Auth, permissions, confirmations |
| DI | `core/di/` | Dishka, `HolixRuntimeConfig` |
| API | `api/gateway.py` | FastAPI, `/v1/chat/completions` |
| CLI | `cli/main.py` | Typer |
| Supervisor | `cli/services/supervisor.py` | `gateway start` в фоне |
| Doctor | `cli/doctor/` | Диагностика |
| TUI | `cli/tui/code/` | Textual UI |
| Слэши | `cli/shared/commands/` | TUI + Telegram `/` |

## Конфигурация

1. **`.env`** — глобальные `Settings` (`config.py`)
2. **Профиль** — `~/.holix/profiles/<имя>/config.yaml`
3. **Флаги CLI** — переопределения на команду

Каталог проекта может дополнять `./.holix/skills`, `.holix/plans`, локальный MCP — не заменяет ключи профиля.

### Идентичность профиля

В `profiles/<имя>/`:

- `SOUL.md` — личность агента (в каждую сессию)
- `USER.md` — факты о пользователе
- `INIT.md` — онбординг до `complete_agent_initialization`

Tools: `save_agent_soul`, `save_user_profile` в `core/tools/profile_identity.py`.

## Точки расширения

- **События** — подписка на `AgentEventBus`
- **Tools** — `BaseTool` + `core/tools/registry.py`
- **Skills** — markdown в `data/skills/`; hub в `data/skills/_hub/`
- **MCP** — имена `mcp_<server>_<tool>` в config

## Интерфейсы

| Интерфейс | Вход |
|-----------|------|
| TUI | `holix tui` |
| Чат | `holix chat-command` |
| Один запрос | `holix run` |
| HTTP | `holix gateway start` |
| Telegram / MAX | companion в gateway |

## См. также

- [CLI.md](CLI.md)
- [GATEWAY.md](GATEWAY.md)
- [MEMORY.md](MEMORY.md) · [MCP.md](MCP.md) · [MODELS.md](MODELS.md)
- [SECURITY.md](SECURITY.md)