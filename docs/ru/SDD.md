# Spec-Driven Development (SDD) в Holix

> **Идея:** сначала спецификация и задачи, потом код, в конце — merge в main specs.  
> Формат совместим с [OpenSpec](https://github.com/javded-itres/OpenSpec).

На этой странице: зачем SDD, дерево `openspec/`, все tools `sdd_*`, slash `/spec`, skills, **режимы apply**, пошаговые **примеры** (CLI/TUI и через агента), multi-project, understanding gate, troubleshooting.

Связанные разделы: [Субагенты](SUBAGENTS.md) · [Слэш-команды](SLASH_COMMANDS.md) · [Hub и навыки](HUB.md) · [Режимы работы](EXECUTION_MODES.md)

---

## Зачем SDD

| Без SDD | С SDD |
|---------|--------|
| Агент сразу пишет код «как понял» | Фиксируется **что** и **зачем**, потом реализация |
| Нет списка задач / исполнителей | `tasks.md` + `assignee` + граф `depends_on` |
| Спеки размазаны по чату | Дельты в `openspec/changes/…`, main — в `openspec/specs/` |
| Сложно делегировать | `sdd_apply` / `sdd_dispatch` → main или субагенты |

Типичные запросы: «добавь OAuth», «переделай API», «спроектируй модуль» — не тривиальный one-liner.

---

## Дерево в workspace

```text
openspec/
  config.yaml
  specs/
    <domain>/
      spec.md                 # source of truth (после archive)
  changes/
    <change-id>/
      proposal.md             # Why / What / Impact
      design.md               # подход, риски
      tasks.md                # чеклист + assignee + depends_on
      specs/
        <domain>/
          spec.md             # delta: ADDED / MODIFIED / REMOVED
      .apply-mode             # self | subagents | hybrid
      .understanding.json     # optional gate
    archive/
      YYYY-MM-DD-<change-id>/ # после sdd_archive
```

**Важно:**

- Нет файла `openspec/changes/<id>/specs.md` — delta только в `specs/<domain>/spec.md`.
- Main-домены (`openspec/specs/`) обновляются **только** через `sdd_archive`, не руками «вперёд».
- Артефакты change заполняйте через **`sdd_write_artifact`**, не через `write_file` (soft gate / неверный формат tasks).

### Multi-project

В одном workspace может быть несколько корней с `openspec/`:

```text
repo/
  openspec/                 # project="" (корень)
  apps/api/openspec/        # project="apps/api"
  apps/web/openspec/        # project="apps/web"
```

1. `sdd_list_projects` → взять `path`
2. Во все `sdd_*` передавать `project=<path>`

---

## Инструменты агента (`sdd_*`)

| Tool | Назначение |
|------|------------|
| `sdd_list_projects` | Список project roots с `openspec/` |
| `sdd_init` | Scaffold `openspec/` (+ example domain) |
| `sdd_list_specs` / `sdd_read_spec` | Main specs (source of truth) |
| `sdd_list_changes` | Активные (и archive) changes |
| `sdd_create_change` | Scaffold change (stubs only!) |
| `sdd_write_artifact` | proposal / design / tasks / specs |
| `sdd_status` | Overview или один change + paths |
| `sdd_update_understanding` / `sdd_confirm_understanding` | Understanding gate |
| `sdd_set_task_assignee` | Назначить `main` / type субагента |
| `sdd_check_task` | Отметить задачу done |
| `sdd_request_apply_mode` / `sdd_set_apply_mode` | self \| subagents \| hybrid |
| `sdd_apply` | Старт apply (план → исполнитель) |
| `sdd_dispatch` | Запуск субагентов по ready-задачам |
| `sdd_archive` | Merge delta → main specs + archive |

---

## Slash `/spec`

В TUI / чате (если зарегистрирован):

```text
/spec
/spec init
/spec propose <change-id>
/spec status [change-id]
/spec mode <change-id> self|subagents|hybrid
/spec apply <change-id>
/spec archive <change-id>
```

Skills (явный запуск или подсказки агенту):

| Skill | Фаза |
|-------|------|
| `/holix-sdd-propose` | spec + tasks, **без кода** |
| `/holix-sdd-apply` | реализация по tasks |
| `/holix-sdd-archive` | merge + archive |

---

## Режимы apply

Выбирает **пользователь** (после готового change), не агент «по умолчанию»:

| Mode | Кто пишет код | Assignees |
|------|----------------|-----------|
| **self** | Только main-агент | Игнорируются (всё на main) |
| **subagents** | Только субагенты по `assignee` | Обязательны; graph `depends_on` |
| **hybrid** | main + субагенты | `main` остаётся на main, остальное — dispatch |

Волны: ready-задачи (deps закрыты) → spawn; после `sdd_check_task` — следующие волны.

---

## Формат `tasks.md` (обязательный)

Только OpenSpec Holix checklist. Свободные `## 1. …` + **Описание**/**Исполнитель** — **отклоняются**.

```markdown
# Tasks: add-oauth

## 1. Backend

- [ ] 1.1 OAuth endpoints
  - **assignee:** `coder`
  - **reason:** изолированный API
  - **depends_on:**

- [ ] 1.2 Shared auth config
  - **assignee:** `main`
  - **reason:** конфликтный shared-код
  - **depends_on:** `1.1`

## 2. Frontend

- [ ] 2.1 Login UI
  - **assignee:** `coder`
  - **reason:** UI после API
  - **depends_on:** `1.1`
```

Правила:

- строка задачи: `- [ ] 1.1 Заголовок`
- вложенно: `**assignee:**`, опционально `**reason:**`, `**depends_on:**`
- parallel: одинаковый `depends_on` (или пустой) у независимых задач
- assignee: `main` | type из `list_subagent_types` | custom agent

### Delta specs (пример)

```markdown
# Spec delta: auth

## ADDED Requirements

### Requirement: OAuth login
The system SHALL allow users to sign in with OAuth 2.0.

#### Scenario: Successful Google login
- **GIVEN** a valid Google account
- **WHEN** the user completes the OAuth redirect
- **THEN** a session is created and the user lands on the dashboard
```

Narrative — на языке пользователя (ru или en), структурные маркеры OpenSpec могут оставаться на EN.

---

## Пример 1 — полный цикл в CLI/TUI (диалог)

**Пользователь:** «Добавь health endpoint `/api/health` в API и тесты».

### Шаг A — propose (спека, без кода)

Агент (схематично):

```text
1) sdd_list_projects
2) sdd_status(project="")          # нет openspec? → sdd_init
3) sdd_list_specs / sdd_read_spec  # brownfield
4) sdd_create_change(
     change_id="api-health",
     request="Добавь GET /api/health и тесты",
     domain="api"                  # или auto
   )
5) [если understanding gate] sdd_update_understanding → вопросы → sdd_confirm_understanding
6) sdd_write_artifact(artifact="proposal", change_id="api-health", content=…)
7) sdd_write_artifact(artifact="specs", domain="api", content=… ADDED Requirements …)
8) sdd_write_artifact(artifact="design", content=…)
9) sdd_write_artifact(artifact="tasks", content=… checklist …)
10) sdd_status(change_id="api-health")
    → apply_ready: true (когда tasks + mode)
```

Агент **останавливается** и ждёт: review + mode.

### Шаг B — mode + apply

```text
Пользователь: /spec mode api-health self
# или
sdd_set_apply_mode(change_id="api-health", mode="self")

Пользователь: /spec apply api-health
# или
sdd_apply(change_id="api-health")
```

Main реализует 1.1, 1.2…:

```text
sdd_check_task(change_id="api-health", task_id="1.1", done=true)
…
```

### Шаг C — archive

```text
sdd_archive(change_id="api-health")
# delta → openspec/specs/api/spec.md
# change → openspec/changes/archive/YYYY-MM-DD-api-health/
```

---

## Пример 2 — multi-project + subagents

Workspace: monorepo `apps/api` + `apps/web`.

```text
sdd_list_projects
# → [{ "path": "apps/api", … }, { "path": "apps/web", … }]

sdd_init(project="apps/api", example_domain="api")
sdd_create_change(
  project="apps/api",
  change_id="rate-limit",
  request="Rate limit 100 req/min per API key"
)
# все дальнейшие вызовы с project="apps/api"
```

`tasks.md`:

```markdown
- [ ] 1.1 Middleware rate limit
  - **assignee:** `coder`
  - **depends_on:**

- [ ] 1.2 Unit tests
  - **assignee:** `coder`
  - **depends_on:** `1.1`

- [ ] 1.3 Review
  - **assignee:** `reviewer`
  - **depends_on:** `1.2`
```

```text
sdd_set_apply_mode(project="apps/api", change_id="rate-limit", mode="subagents")
sdd_apply(project="apps/api", change_id="rate-limit")
sdd_dispatch(project="apps/api", change_id="rate-limit")
# волна 1: coder на 1.1
# после check 1.1 → 1.2
# после check 1.2 → reviewer 1.3
sdd_archive(project="apps/api", change_id="rate-limit")
```

---

## Пример 3 — hybrid (shared + parallel)

```markdown
- [ ] 1.1 Shared auth types
  - **assignee:** `main`
  - **depends_on:**

- [ ] 2.1 API handlers
  - **assignee:** `coder`
  - **depends_on:** `1.1`

- [ ] 2.2 CLI command
  - **assignee:** `coder`
  - **depends_on:** `1.1`
```

Mode **hybrid**: main делает 1.1; 2.1 и 2.2 стартуют **параллельно** после 1.1 (два job `coder-1`, `coder-2`).

---

## Understanding gate (если включён)

Перед полным propose агент **не** должен сразу засыпать вопросами:

1. Прочитать main specs + archive (`sdd_list_changes include_archive=true`)
2. Контекст проекта / `HOLIX.md` (при необходимости `/init`)
3. `sdd_update_understanding` с честным `score` 0–100
4. Только residual-вопросы в чат
5. При score ≥ threshold → `sdd_confirm_understanding`
6. Затем `sdd_write_artifact`

Пока gate `clarifying` / не confirmed — `sdd_write_artifact` для полного propose **блокируется**.

---

## Типичный happy path (чеклист)

```text
[ ] sdd_list_projects / project=
[ ] sdd_init (если нужно)
[ ] sdd_list_specs + sdd_read_spec
[ ] sdd_create_change(change_id, request=)
[ ] understanding (если on) → confirm
[ ] sdd_write_artifact × proposal, specs, design, tasks
[ ] sdd_status → apply_ready
[ ] USER: mode self|subagents|hybrid
[ ] sdd_apply → (sdd_dispatch) → implement → sdd_check_task*
[ ] sdd_archive
```

---

## Чего не делать

| Ошибка | Как правильно |
|--------|----------------|
| Сразу `write_file` в исходники «по фиче» | Сначала change + apply |
| `write_file` в `openspec/changes/…` | `sdd_write_artifact` |
| `specs.md` в корне change | `artifact=specs` + `domain=` |
| Free-form tasks | Checklist `- [ ]` + `**assignee:**` |
| `sdd_archive` до готовности | Все tasks done + review |
| Propose на EN, чат на RU | Один locale (ru **или** en) |
| create_change = «спека готова» | Это только stubs — нужен write_artifact |

---

## Troubleshooting

| Симптом | Решение |
|---------|---------|
| `apply_ready: false` | Не заполнены artifacts / mode / unassigned tasks (для subagents) |
| tasks rejected | Только OpenSpec checklist format |
| `understanding` block | score / confirm / gate prefs |
| Wrong paths / file not found | `sdd_status(change_id)` → `artifact_paths` |
| Subagents не стартуют | mode subagents/hybrid; ready deps; `sdd_dispatch` |
| Soft gate write_file | Выбрать apply mode до массовых правок |

---

## Связь с субагентами

- Типы: `list_subagent_types` → `coder`, `reviewer`, custom…
- Для SDD предпочтительны `sdd_apply` / `sdd_dispatch`, а не «голый» `delegate_to_subagent` без graph
- После `sdd_check_task(done=true)` связанные running subagents могут отменяться

Подробнее: [SUBAGENTS.md](SUBAGENTS.md).

---

## Краткий reference для агента

```text
sdd_list_projects
sdd_init(project="", example_domain="app")
sdd_create_change(change_id="feature-x", request="…", project="")
sdd_write_artifact(change_id="feature-x", artifact="proposal", content="…")
sdd_write_artifact(change_id="feature-x", artifact="specs", domain="app", content="…")
sdd_write_artifact(change_id="feature-x", artifact="tasks", content="…")
sdd_set_apply_mode(change_id="feature-x", mode="self")
sdd_apply(change_id="feature-x")
sdd_check_task(change_id="feature-x", task_id="1.1", done=true)
sdd_archive(change_id="feature-x")
```

Фраза пользователю: «Начни SDD: `/spec propose …`» или «Используй skill holix-sdd-propose».
