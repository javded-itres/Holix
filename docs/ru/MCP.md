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

Если для агента задан список `mcp_assignments`, загружаются только эти серверы. Без списка доступны все настроенные.

## Наложение workspace

Попросите агента подключить сервер: он запишет `<workspace>/.holix/config.yaml` (`workspace_holix`). Каталог `~/.holix/profiles` агент не читает.

Ссылку можно отправить прямо в чат. Репозиторий GitHub или GitLab со `SKILL.md`, а также ссылка skills.sh, ClawHub или на сам `SKILL.md`, ставится как скилл workspace. Репозиторий с `mcp` в имени или с точкой входа MCP и без `SKILL.md` ставится как stdio-сервер. Адрес `https://…/mcp` подключается через `mcp-remote`. Адрес `https://…/sse` остаётся на SSE-клиенте.

```yaml
mcp_servers:
  context7:
    transport: stdio
    command: npx
    args: ["-y", "@upstash/context7-mcp"]
```

Имя, которое уже есть в профиле, заменяется этим файлом. Новое имя добавляется; если у `main` есть список допуска, имя дописывается туда. Блок `mcp_assignments` в том же файле заменяет список этого слота. Модель, провайдеры и auth из файла игнорируются. Изменённая команда уже подключённого сервера применяется после перезапуска gateway.

---

## Удалённый HTTP (`mcp-remote`)

Клиент Holix говорит на stdio и на старом SSE. Сервер Streamable HTTP добавляется как `transport: http`. При старте Holix запускает `npx -y mcp-remote <url>`: это процесс stdio, который сначала говорит по HTTP и при необходимости переходит на SSE.

```yaml
mcp_servers:
  docs:
    transport: http
    url: https://example.com/mcp
    headers:
      Authorization: "Bearer ${DOCS_TOKEN}"
```

Для адреса `http://` добавляется `--allow-http` (своя сеть или loopback). Значение заголовка уходит в `mcp-remote` как `--header Name:${ENV}`, без секрета в командной строке. `holix mcp list` показывает URL, а не команду моста.

## Установка из git

```bash
holix mcp install https://github.com/org/my-mcp-server
holix mcp add my-custom
holix mcp add docs --transport http --url https://example.com/mcp
holix mcp add docs --transport http --url http://127.0.0.1:4000/mcp --header "Authorization: Bearer $TOKEN"
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
