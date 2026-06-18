# Субагенты Holix

Фоновые воркеры для **специализированных задач** без блокировки основного чата. В Holix есть **готовые типы** субагентов (`researcher`, `coder`, …); вы **запускаете** их на задачу — новый тип через UI не создаётся.

## Включение

В `config.yaml` профиля или глобальном `.env`:

```yaml
enable_subagents: true
subagent_default_process_mode: process   # process | async
subagent_max_concurrent: 4
subagent_process_timeout: 120
```

По умолчанию: `enable_subagents: true`.

Если выключено — `delegate_to_subagent` и `/subagent-spawn` вернут ошибку.

---

## Встроенные типы

| Тип | Роль | Основные tools |
|-----|------|----------------|
| `researcher` | Исследование, файлы, веб | `web_search`, `web_fetch`, `read_file`, `list_directory` |
| `web_researcher` | Поиск в интернете и синтез | `web_search`, `web_fetch` |
| `coder` | Код, правки, отладка | `read_file`, `write_file`, `terminal`, `code_executor` |
| `analyst` | Данные / SQL | `sql_query`, `sql_schema`, `code_executor`, `math_calculator` |
| `reviewer` | Ревью кода | `read_file`, `list_directory`, `terminal` |
| `writer` | Документация и тексты | `read_file`, `write_file`, `list_directory` |

Встроенные типы: `core/subagents/registry.py` (`PREDEFINED_SUBAGENTS`).

---

## Создать новый тип субагента

В Holix **тип** (роль, промпт, tools) отделён от **экземпляра** (запущенный воркер).

### TUI (рекомендуется)

В `holix tui`:

```text
/subagent-types
```

Откроется менеджер, где можно задать:

| Поле | Назначение |
|------|------------|
| **Имя** | Уникальный slug (`security-auditor`) — не `coder`, `researcher`, … |
| **Системный промпт** | Роль и правила поведения |
| **Tools** | Инструменты Holix (`read_file`, `terminal`, `web_search`, …) |
| **Skills** | Allowlist навыков профиля для типа (`skill_assignments`) |
| **MCP** | MCP-серверы из `mcp_servers` профиля |
| **Слот модели** | Пресет из `agent_models` или модель родителя |
| **Внешний CLI** | Привязка `holix launch` (Claude Code, OpenCode, …) |

Хранится в профиле:

`~/.holix/profiles/<profile>/subagents/types.json`

При сохранении обновляются `skill_assignments`, `mcp_assignments`, привязки external CLI и при необходимости `agent_models`.

Список типов в чате:

```text
/subagent-types list
```

Запуск:

```text
/subagent-spawn security-auditor Проверь auth-модуль на OWASP-риски
```

### Код (встроенный тип)

Чтобы добавить **встроенный** тип в дистрибутив Holix — запись в `PREDEFINED_SUBAGENTS` в `core/subagents/registry.py`. После правки репозитория перезапустите Holix.

---

## Запуск субагента (создание экземпляра)

«Создать субагента» = **запустить воркер** выбранного типа с формулировкой задачи.

### Слэш-команды в TUI

```text
/subagent-spawn coder Исправь падающие тесты в tests/
/subagents
/subagent-result coder
/subagent-terminate coder
```

| Команда | Действие |
|---------|----------|
| `/subagents` | Список активных и недавних job |
| `/subagent-spawn <тип> <задача>` | Запуск в фоне |
| `/subagent-result <job_id>` | Ответ завершённого воркера |
| `/subagent-terminate <job_id>` | Остановить |
| `/subagent-reply <job_id> <текст>` | Ответ субагенту (после `ask_user`) |

Если `coder` уже занят — появятся `coder-2`, `coder-3`, …

### Главный агент (автоматически)

Например в чате:

```text
Запусти в фоне researcher: собери документацию по API модуля auth
```

Главный агент вызовет `delegate_to_subagent`, вернёт `job_id` и при необходимости `wait_subagent_result`.

Tools главного агента (при `enable_subagents: true`):

- `delegate_to_subagent`
- `wait_subagent_result`
- `list_subagents`
- `terminate_subagent`

### Режимы Plan / Hybrid

При `enable_subagents: true` план может делегировать шаги субагентам (`researcher` → `coder` → `reviewer`). См. [EXECUTION_MODES.md](EXECUTION_MODES.md).

---

## Модель выполнения

| Режим | Поведение |
|-------|-----------|
| `process` (по умолчанию на Linux/macOS) | Отдельный OS-процесс — параллелизм и изоляция |
| `async` | Задача `asyncio` в процессе Holix — меньше накладных расходов |

Настраивается через `subagent_default_process_mode`.

Субагент использует **модель родителя** (`config.model`), не слоты `agent_models` (если не расширять реестр).

---

## Внешние CLI (опционально)

`external_cli` субагенту **не выдаётся автоматически**. Чтобы субагент запускал Claude Code / OpenCode в tmux:

1. `holix launch setup` или `/launch` в TUI — назначить CLI типу субагента (`agent_slot`, например `coder`)
2. Делегировать задачу этому субагенту — при назначении появится tool `external_cli`

Настройка: [LAUNCH.md](LAUNCH.md). TUI: `/launch` — назначение CLI типу субагента.

### Субагенты и `holix launch`

| | Субагенты Holix | `holix launch` (tmux) |
|---|---|---|
| **Что** | Фоновые воркеры Holix | Внешние CLI (Claude Code, OpenCode, …) |
| **Старт** | `delegate_to_subagent` / `/subagent-spawn` | `holix launch <id>` или `external_cli` у назначенного субагента |
| **Модель** | Модель родительского профиля | Слот (`agent_models.coder`, …) |

Главный агент **не** получает `external_cli` напрямую — только субагент с назначением в `holix launch setup` или TUI `/launch`.

---

## Логи и лимиты

- Лог: `logs/subagent.jsonl` — см. [LOGS.md](LOGS.md)
- CLI: `holix logs -s subagent`
- Параллельно: не больше `subagent_max_concurrent` (по умолчанию 4)
- Таймаут job: `subagent_process_timeout` (секунды)

---

## Пример

```bash
holix tui
```

```text
/subagent-spawn web_researcher Сравни Holix с похожими агентами; укажи источники
/subagents
/subagent-result web_researcher
```

Или одним сообщением главному агенту:

```text
Делегируй coder: добавь type hints в cli/commands/launch.py и прогони тесты
```

---

## См. также

- [LAUNCH.md](LAUNCH.md) — `holix launch` и tmux-сессии
- [SLASH_COMMANDS.md](SLASH_COMMANDS.md) — все `/`-команды
- [EXECUTION_MODES.md](EXECUTION_MODES.md) — Plan / Hybrid
- [LOGS.md](LOGS.md) — `subagent.jsonl`