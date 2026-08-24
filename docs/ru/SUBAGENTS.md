# Субагенты Holix

Фоновые воркеры для **специализированных задач** без блокировки основного чата. В Holix есть **готовые типы** (`researcher`, `coder`, …). Вы **запускаете** джоб выбранного типа. Типы также можно **создавать и править** в TUI и в Telegram/MAX (ниже).

## Включение

В `config.yaml` профиля или глобальном `.env`:

```yaml
enable_subagents: true
subagent_default_process_mode: async   # async | process
subagent_max_concurrent: 4
subagent_process_timeout: 3600
subagent_supervisor_enabled: true
subagent_supervisor_max_interventions: 3
```

По умолчанию: `enable_subagents: true`, режим процесса **`async`** (OS process доступен с fallback).

Если выключено — `delegate_to_subagent` и `/subagent-spawn` вернут ошибку.

## Исполнение (тот же ReAct, что у main)

Каждый джоб — дочерний `HolixAgent` на **том же LangGraph ReAct**, что и основной чат (`memory_retrieval → react → tools → finalize`):

- тот же `react_node` (сжатие контекста, action honesty, nudge «шаг не закончен»)
- урезанный набор tools (`FilteredToolRegistry`) — ребёнок не спавнит субагентов
- окно контекста — **модели** (`model_contexts` / слот / профиль), как у main; сжатие на 85% этого окна
- пустой ответ модели **не** завершает шаг: ReAct трижды говорит «продолжай», затем джоб падает с `empty LLM reply`
- runtime-супервизор вшивает `guidance` / `revise` в тот же шаг ReAct (и уважает `cancel`)

Если дочерний ReAct не стартовал — fallback на старый цикл.

---

## Встроенные типы

| Тип | Роль | Основные tools |
|-----|------|----------------|
| `researcher` | Исследование, файлы, веб | `web_search`, `web_fetch`, `read_file`, `list_directory` |
| `web_researcher` | Поиск в интернете и синтез | `web_search`, `web_fetch` |
| `coder` | Код, правки, отладка | `read_file`, `patch_file`, `write_file`, `terminal`, `code_executor` |
| `analyst` | Данные / SQL | `sql_query`, `sql_schema`, `code_executor`, `math_calculator` |
| `reviewer` | Ревью кода | `read_file`, `list_directory`, `terminal` |
| `writer` | Документация и тексты | `read_file`, `patch_file`, `write_file`, `list_directory` |

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

TUI — полная форма (skills, MCP, external CLI). В мессенджерах: личность, модель, температура, tools и Code mode, в том числе для **системных** типов через оверлей (`subagents/overlays.json`).

### Telegram и MAX

В статус-меню пункт **Субагенты**, либо `/code-mode` / `/subagent-types`.

| Действие | Что происходит |
|----------|----------------|
| Code mode (`native` / `code` / `both`) | `tools_presentation` профиля для `main` или override на тип. Подробнее: [CODE_MODE.md](CODE_MODE.md) |
| Создать по описанию | Одно сообщение с ролью. Тип пишется в `types.json` и сразу в списке |
| Системный тип | Личность (сгенерировать или вставить), слот модели, температура, tools, Code mode. **Сбросить** удаляет оверлей |
| Свой тип | Те же поля плюс **Удалить** |
| Tools | Включение/выключение. Лишние системные tools (background process) не сбрасываются, пока вы не перезапишете список |

Skills, MCP и external CLI остаются в TUI — в клавиатуру мессенджера они не влезают.

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

`fork=true` (или `/subagent-spawn --fork`) передаёт ребёнку **завершённые ходы родителя**, без текущего tool-вызова. У ребёнка свои tools, PTY, todos и пресет `/permission`. По умолчанию — **новая** беседа.

Внешний **ACP**-агент (не тип Holix): `run_acp_agent(prompt)`. Задайте `HOLIX_ACP_COMMAND` (например `grok --acp`). См. [ACP.md](ACP.md).

Tools главного агента (при `enable_subagents: true`):

- `delegate_to_subagent`
- `wait_subagent_result`
- `list_subagents`
- `terminate_subagent`

### Режимы Plan / Hybrid

При `enable_subagents: true` план может делегировать шаги субагентам (`researcher` → `coder` → `reviewer`). См. [EXECUTION_MODES.md](EXECUTION_MODES.md).

В **`plan_and_execute`** возможны **волны** субагентов и цикл **supervisor** до синтеза:

```text
delegate → collect → supervisor → (rework failed?) → react synthesis
```

---

## Supervisor

Два уровня помощи застрявшим воркерам.

### 1. Runtime supervisor (во время job)

Фоновый watcher при первом spawn (`core/subagents/supervisor.py`):

| Детект | Действие |
|--------|----------|
| **Loop** — один и тот же tool+args | Guidance в тот же job |
| **Thrash** — только ошибки tools | Не повторять; чинить причину |
| **Hung** — нет activity `idle_s` | Подтолкнуть к финалу / смене стратегии |
| **Stall** — шаги без прогресса | Сузить задачу |

Лимиты: max interventions, cooldown. Событие: `SubAgentSupervisorEvent`.

| Переменная | Default | Смысл |
|------------|---------|--------|
| `HOLIX_SUBAGENT_SUPERVISOR_ENABLED` | `true` | Вкл/выкл |
| `HOLIX_SUBAGENT_SUPERVISOR_POLL_S` | `4` | Интервал опроса |
| `HOLIX_SUBAGENT_SUPERVISOR_IDLE_S` | `300` | Порог hang (долгий LLM ≠ hang) |
| `HOLIX_SUBAGENT_SUPERVISOR_MAX_INTERVENTIONS` | `3` | Лимит на job / rework |
| `HOLIX_SUBAGENT_SUPERVISOR_COOLDOWN_S` | `45` | Пауза между вмешательствами |

### 2. Graph supervisor (после волны)

После `collect_subagent` в plan mode:

1. Смотрит результаты волны.
2. Failed jobs → **rework** того же `agent_type` с инструкциями.
3. Успешные jobs сохраняются; failed `prior_job` заменяется.
4. Синтез в `react`.

План: [SUBAGENT_SUPERVISOR.md](../en/SUBAGENT_SUPERVISOR.md).
Общий step-budget: [EXECUTION_MODES.md](EXECUTION_MODES.md).

---

## Модель выполнения

| Режим | Поведение |
|-------|-----------|
| `async` (по умолчанию) | Задача `asyncio` в процессе Holix — меньше накладных расходов |
| `process` | Отдельный OS-процесс — сильнее изоляция; возможен fallback на async |

Настраивается через `subagent_default_process_mode`.

По умолчанию субагент использует **модель родителя**. Если в профиле есть слот `agent_models.<тип>` (например `coder`) или у кастомного типа задан **слот модели**, берётся он.

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
| **Модель** | Слот `agent_models.<тип>` если задан, иначе модель родителя | Слот (`agent_models.coder`, …) |

Главный агент **не** получает `external_cli` напрямую — только субагент с назначением в `holix launch setup` или TUI `/launch`.

---

## Логи и лимиты

- Лог: `logs/subagent.jsonl` — см. [LOGS.md](LOGS.md)
- CLI: `holix logs -s subagent`
- Параллельно: не больше `subagent_max_concurrent` (по умолчанию 4)
- Таймаут job: `subagent_process_timeout` (секунды; по умолчанию `3600`, 60 мин)
- Wait-бюджет может продлеваться при активной работе
- Вмешательства supervisor видны в activity и agent events

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
