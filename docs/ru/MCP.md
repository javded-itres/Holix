# Model Context Protocol (MCP)

Holix подключает внешние **MCP-серверы** (stdio или SSE) и отдаёт их инструменты агенту как `mcp_<сервер>_<инструмент>`.

Настройка **на профиль** в `config.yaml`: `mcp_servers` и `mcp_assignments`.

---

## Требования

- **Node.js** и `npx` для многих серверов — проверка в `holix doctor`
- Опционально: **Docker** для контейнерных MCP

---

## Быстрый старт

```bash
holix mcp setup
holix mcp list-popular
holix mcp install filesystem
holix mcp test my-server
holix doctor
```

В TUI/Telegram: `/mcp`, `/mcp install`, `/mcp assign` — [SLASH_COMMANDS.md](SLASH_COMMANDS.md).

CLI: [CLI.md](CLI.md#mcp).

---

## Конфигурация (`config.yaml`)

```yaml
mcp_servers:
  filesystem:
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/workspace"]
  my-sse:
    transport: sse
    url: http://127.0.0.1:3001/sse

mcp_assignments:
  main: [filesystem]
  coder: [filesystem, my-sse]
```

| Поле | Назначение |
|------|------------|
| `mcp_servers` | Описание серверов |
| `mcp_assignments` | Какие агенты (`main`, `coder`, …) получают какие серверы |

Инструменты в рантайме: **`mcp_<сервер>_<имя>`**.

```bash
holix mcp add
holix mcp assign
holix config edit
holix profile global edit
```

---

## Назначение агентам

| Слот | Когда |
|------|-------|
| `main` | Основной чат |
| `coder`, `researcher`, … | Субагенты — [SUBAGENTS.md](SUBAGENTS.md) |
| Свои типы | `/subagent-types` |

Загружаются только серверы из `mcp_assignments` для активного агента.

---

## Установка из git

```bash
holix mcp install https://github.com/org/my-mcp-server
holix mcp add my-custom
```

Перед работой в чате: `holix mcp test <имя>`.

---

## Gateway API

`GET/POST /api/holix/profiles/{id}/mcp` — [GATEWAY_API.md](GATEWAY_API.md).

---

## Решение проблем

| Проблема | Действие |
|----------|----------|
| Нет tools в чате | `holix mcp list`; проверьте `mcp_assignments` |
| `npx` не найден | Node.js; `holix doctor --fix` |
| Сервер не стартует | `holix mcp test <имя>`; путь и env в конфиге |
| Placeholder в env | `holix doctor` |

---

## См. также

- [HUB.md](HUB.md) — навыки (не MCP)
- [CONFIGURATION.md](CONFIGURATION.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)