# План: Spec-Driven Development в Holix Studio (по OpenSpec)

> Источник модели: [OpenSpec](https://github.com/javded-itres/OpenSpec) (форк Fission-AI/OpenSpec).  
> Цель: SDD в Studio — работа начинается со спецификации, реализация и archive вливают изменения в main specs.  
> Статус: реализовано foundation + Studio API/UI (PR1–PR6 core).  
> Дата: 2026-07-18.

---

## 1. Что даёт OpenSpec (целевое поведение)

OpenSpec — это **не** «ещё один plan mode», а **постоянный контракт продукта** в репозитории:

| Идея | Как в OpenSpec | Как должно быть в Studio |
|------|----------------|---------------------------|
| Source of truth | `openspec/specs/**/spec.md` | Спеки живут **в workspace** (git), не только в чате |
| Единица работы | `openspec/changes/<id>/` | Change = задача/фича с артефактами |
| Сначала согласие | proposal → specs → design → tasks | Агент **не кодит**, пока change не «apply-ready» |
| Реализация | `/opsx:apply` по `tasks.md` | Implement только из tasks + delta specs |
| Исполнители | (нет в OpenSpec) | В `tasks.md` помечать, **какой субагент** берёт задачу |
| Режим apply | (нет) | **Перед apply** спросить: сам main-агент или субагенты |
| Закрытие | archive: merge delta → main specs | После done — merge + archive |
| Новая работа | сначала read main specs | Перед новым change — обзор `specs/` |

**Цепочка артефактов (enablers, не жёсткий waterfall):**

```text
explore (опц.) → propose → [specs, design, tasks + assignee]
       → ask: self | subagents → apply (implement) → archive
```

**Важно:** текущий Holix `plan_and_execute` — это **runtime-план одного прогона**. OpenSpec — **durable SDD в файлах**. Их нужно **связать**, а не заменить друг другом:

```text
SDD (файлы)          →   Agent run (graph)
specs + change       →   tasks.md как backlog (+ assignee)
apply mode           →   main agent | subagents (выбор user)
archive              →   обновлённый source of truth
```

---

## 2. Цели продукта (DoD для фичи)

1. В workspace появляется дерево спецификаций (совместимое с OpenSpec layout — проще CLI/interop).
2. Любая **нетривиальная** задача в Studio проходит:  
   **прочитать main specs → создать/обновить change → review → implement → archive**.
3. Агент и UI **видят** статус change (какие артефакты есть, % tasks, apply-ready, **assignee**).
4. В `tasks.md` при propose/уточнении спеки у каждой задачи указан исполнитель: `main` или тип/имя субагента.
5. **Перед apply** Studio/агент **явно спрашивает**: выполнять задачи самостоятельно (main) или раздавать субагентам (по разметке / с подтверждением).
6. После archive delta-требования **вливаются** в `specs/`, change уходит в `archive/`.
7. Пользователь может вести SDD **из UI** (панель Specs) и **из чата** (`/spec …` / skills).

**Не цели v1:** полный порт Node CLI OpenSpec, multi-repo Stores, pixel-perfect OPSX slash-команды.

---

## 3. Рекомендуемая модель данных (в workspace)

Совместимость с OpenSpec — осознанный выбор (можно позже звать `openspec` CLI):

```text
<workspace>/
  openspec/
    config.yaml                 # schema, rules, context
    specs/
      <domain>/
        spec.md                 # Requirements + Scenarios (GIVEN/WHEN/THEN)
    changes/
      <change-id>/
        proposal.md
        design.md               # опционально по schema
        tasks.md                # checklist + assignee (main | subagent)
        specs/
          <domain>/
            spec.md             # delta: ## ADDED/MODIFIED/REMOVED Requirements
      archive/
        YYYY-MM-DD-<change-id>/
```

**Формат requirements** (как в OpenSpec):

- `### Requirement: …` + SHALL/MUST  
- `#### Scenario: …` + GIVEN/WHEN/THEN  
- Delta: секции ADDED / MODIFIED / REMOVED  

**Формат `tasks.md` (Holix-расширение OpenSpec):**

При построении спецификации (propose / refine) каждая задача **обязана** иметь метку исполнителя — кто *предполагается* для apply:

```markdown
## 1. Backend

- [ ] 1.1 Add OAuth endpoints
  - **assignee:** `api-dev`          # имя/тип субагента из registry
  - **reason:** isolated API surface

- [ ] 1.2 Wire session store
  - **assignee:** `main`             # делает главный агент
  - **reason:** touches shared auth config

## 2. Frontend

- [ ] 2.1 Login form
  - **assignee:** `ui-dev`
```

Допустимые значения `assignee`:

| Значение | Смысл |
|----------|--------|
| `main` | Главный агент сессии (без субагента) |
| `<subagent-type>` / `<name>` | Тип или зарегистрированное имя субагента (как в Holix subagents registry) |
| `unassigned` | Временно; apply-ready **только** если user явно выберет режим (или принудительно main) |

Правила propose:

1. Разбивать работу так, чтобы параллелимые куски уходили разным субагентам.  
2. Shared / risky / merge-conflict зоны — по умолчанию `main` или один owner.  
3. В `design.md` (кратко) — таблица «task → assignee → why».  
4. Список доступных типов субагентов брать из registry Studio/Helix на момент propose.

**`config.yaml` (минимум):**

```yaml
schema: holix-spec   # или spec-driven
context: |
  Project: …
rules:
  proposal: |
    Keep under 500 words; Why / What / Impact
  specs: |
    Scenario-first; no implementation detail
  tasks: |
    Small checkboxes; group by phase;
    every task MUST have assignee: main | <subagent-type>;
    prefer subagents for independent workstreams
apply:
  # Перед apply всегда спрашивать (default), если не задано иное
  ask_execution_mode: true   # self | subagents | hybrid
  default_mode: ask          # ask | self | subagents | hybrid
```

Опционально позже: `schemas/holix-spec/schema.yaml` (как OpenSpec custom schemas) — для v1 хватит built-in chain.

---

## 4. Архитектура в Holix / Studio

```text
┌─────────────────────────────────────────────────────────┐
│  Studio UI                                              │
│  • Specs panel (domains, changes, tasks + assignee)     │
│  • Slash /spec propose|status|apply|archive             │
│  • Gate: «нет change» → предложить propose              │
│  • Apply dialog: self | subagents | hybrid              │
└───────────────────────────┬─────────────────────────────┘
                            │ HTTP / events
┌───────────────────────────▼─────────────────────────────┐
│  Helix: SDD module                                      │
│  • SpecStore (read/write workspace files)               │
│  • ChangeLifecycle (new, status, archive, merge)        │
│  • Task assignees parse + apply execution mode          │
│  • Tools: list_specs, create_change, get_change_status, │
│           write_artifact, check_task, archive_change    │
│  • Skills: holix-spec-propose / apply / archive         │
│  • Policy: before code tools, require apply-ready change│
│  • Apply: dispatch tasks → main and/or SubagentManager  │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│  Workspace FS + Git          Subagents registry/monitor │
│  openspec/** as source of truth                         │
└─────────────────────────────────────────────────────────┘
```

### 4.1 Helix (core)

| Компонент | Назначение |
|-----------|------------|
| `core/sdd/` или `core/openspec/` | Парсинг/запись specs, merge deltas, status, **assignees** |
| Tools (agent) | Агент сам ведёт lifecycle через tools |
| Skills (prompt packs) | Как OPSX skills: propose / apply / archive |
| Graph hooks | Перед `write_file`/`shell` на feature-work — soft gate |
| Subagent dispatch | При mode=subagents/hybrid: spawn по `assignee` из tasks |
| Events | `sdd.change_created`, `sdd.task_done`, `sdd.archived`, `sdd.apply_mode_chosen` → Studio |

### 4.2 Studio

| Поверхность | Назначение |
|-------------|------------|
| Tab **Specs** (рядом с Subagents / Files) | Дерево domains + changes + preview markdown |
| Change detail | proposal/design/tasks + progress + **assignee badges** |
| **Apply dialog** | Обязательный вопрос: сам / субагенты / hybrid; превью «task → who» |
| Chat integration | Slash + system hints «сначала specs»; перед apply — вопрос в чате |
| Init wizard | «Initialize SDD in workspace» → scaffold `openspec/` |
| Optional gate UI | Confirm before first code after propose |

### 4.3 Связь с plan_and_execute и subagents

| Этап SDD | Agent mode |
|----------|------------|
| propose (артефакты) | `react` / `plan` **без** широкого coding; tasks с **assignee** |
| **pre-apply** | **Спросить user:** `self` \| `subagents` \| `hybrid` (см. §5.E) |
| apply (self) | main: `plan_and_execute` / `react`, backlog = **tasks.md** |
| apply (subagents) | main: orchestrator; spawn subagents по assignee; monitor tab |
| apply (hybrid) | `main`-tasks у main; остальные — субагентам по разметке |
| archive | короткий react-run: merge + move + git commit (опц.) |

Runtime plan steps ≠ `tasks.md`. При apply: **синхронизировать** — либо agent отмечает tasks в `tasks.md`, либо Studio чекбоксы пишут в файл.  
Субагент по завершении task → `sdd_check_task` / event → обновление checklist.

---

## 5. Пользовательские сценарии (UX)

### A. Новая фича

1. User: «Добавь OAuth login»  
2. Agent: читает `openspec/specs/**`  
3. Agent: `/spec propose oauth-login` → change + proposal/specs/design/**tasks с assignee**  
4. Studio: показывает change (кто какой task), user правит/Approve  
5. User: «Implement» / `/spec apply`  
6. **Стоп: вопрос режима выполнения** (см. E)  
7. По выбранному режиму — main и/или субагенты идут по `tasks.md`, чекают пункты  
8. User/Agent: `/spec archive` → merge в main specs  

### B. Мелкий bugfix

- Если change не нужен (tiny): skill говорит «skip SDD» (как OpenSpec fluid).  
- Порог: config `sdd.require_for: [feature, api, schema]` vs `always` / `never`.  
- Для tiny без change вопрос про субагентов **не** обязателен.

### C. Brownfield bootstrap

1. «Initialize SDD»  
2. Agent сканирует код → черновики `specs/<domain>/spec.md`  
3. User review → commit  

### D. После завершения задачи

- Все tasks `[x]` → UI: «Archive change?»  
- Archive: merge deltas → `specs/`, move to `archive/YYYY-MM-DD-…`  
- Optional: auto-commit message `docs(sdd): archive <change-id>`

### E. Выбор режима выполнения (обязательный pre-apply)

**Когда:** сразу перед первым coding-шагом apply (slash `/spec apply`, кнопка Apply, или user «делай»).  
**Не когда:** propose-only, explore, archive.

Агент / UI формулирует примерно так:

> Change `oauth-login` готов к apply.  
> Задачи: 4 (main: 1, api-dev: 2, ui-dev: 1).  
> Как выполнять?
>
> 1. **Самостоятельно** — все задачи делает main-агент (assignee в tasks игнорируется или используется только как подсказка).  
> 2. **На субагентах** — по разметке `assignee` (tasks с `main` остаются у main).  
> 3. **Hybrid** — строго по `assignee` (`main` + субагенты).  
>
> (Опционально) Переназначить задачи перед стартом.

| Режим | Поведение |
|-------|-----------|
| `self` | Один main-агент; субагенты не стартуют |
| `subagents` | Все non-`main` → spawn; `main` → orchestrator/main |
| `hybrid` | Как subagents, но явно подчёркнуто: main тоже делает свои tasks |

Правила:

1. **Не начинать coding**, пока user не ответил (chat choice / Apply dialog / flag в API).  
2. Ответ сохранять в change metadata (например `changes/<id>/.apply-mode` или frontmatter) на время run.  
3. Если user выбрал `subagents`/`hybrid`, а assignee неизвестен registry — спросить переназначение или fallback `main`.  
4. В Specs panel / Subagents monitor: связь `task_id` ↔ `subagent_run_id`.  
5. Config `apply.ask_execution_mode: false` + `default_mode` — только для power-user/automation; **default = ask**.

---

## 6. Agent policy (сердце SDD)

В system prompt / skill **holix-sdd** (аналог OPSX):

1. **Перед новой работой:** `list_specs` + `list_changes`; не дублировать open change.  
2. **Нет change и work non-trivial:** создать propose (не сразу code).  
3. **Есть proposal, нет specs:** дописать delta specs.  
4. **При tasks:** у **каждой** задачи выставить `assignee` (main или subagent type/name) + краткий reason; сверять типы с registry.  
5. **Перед apply:** **обязательно спросить** user: self / subagents / hybrid; не кодить до ответа.  
6. **Apply:** только tasks; сверяться с delta specs; отмечать checkbox; spawn по выбранному режиму.  
7. **Done:** предложить archive; не оставлять «висящий» change.  
8. **Explore:** можно без файлов (как `/opsx:explore`).

**Soft gate (v1):** warning tool result / UI banner, не hard-block (OpenSpec: fluid).  
**Hard gate (v2, optional):** block `write_file` outside `openspec/` until apply-ready **and** execution mode chosen.

---

## 7. API / tools (контракт)

Минимальный набор tools (Helix):

| Tool | Поведение |
|------|-----------|
| `sdd_init` | Создать `openspec/` + config + example domain |
| `sdd_list_specs` | Список domains + summary requirements |
| `sdd_read_spec` | Читать domain spec |
| `sdd_list_changes` | active + optional archive |
| `sdd_create_change` | `changes/<id>/` scaffold |
| `sdd_status` | Artifacts ready, task progress, assignees summary, apply-ready |
| `sdd_write_artifact` | proposal/design/tasks/delta spec |
| `sdd_set_task_assignee` | Назначить/сменить `assignee` у task |
| `sdd_check_task` | Toggle `- [ ]` / `- [x]` by index/id |
| `sdd_request_apply_mode` | Задать вопрос user / вернуть pending choice |
| `sdd_set_apply_mode` | Зафиксировать `self` \| `subagents` \| `hybrid` |
| `sdd_apply` | Старт apply **только** если mode выбран; dispatch |
| `sdd_archive` | Merge deltas → main, move to archive |

Studio HTTP (тонкий слой):

- `GET /api/sdd/status`  
- `GET /api/sdd/specs`  
- `GET /api/sdd/changes`  
- `GET /api/sdd/changes/{id}/tasks` — checklist + assignees  
- `POST /api/sdd/init`  
- `POST /api/sdd/changes`  
- `PATCH /api/sdd/changes/{id}/tasks/{task_id}` — assignee / done  
- `POST /api/sdd/changes/{id}/apply` — body: `{ "mode": "self"|"subagents"|"hybrid" }`  
- `POST /api/sdd/changes/{id}/archive`  

Реализация merge: Python port логики «ADDED/MODIFIED/REMOVED → main spec» (не обязателен Node). Опционально: если `openspec` CLI в PATH — shell wrapper для parity.

---

## 8. UI Studio (фазы экрана)

**v1 — Files-first + slash**  
- Scaffold + skills + tools  
- Пользователь смотрит markdown в Files (tasks с assignee)  
- Slash: `/spec propose`, `/spec apply`, `/spec archive`, `/spec status`  
- `/spec apply` **всегда** сначала спрашивает self vs subagents (чат)

**v2 — Specs panel**  
- Sidebar: Specs | Changes  
- Markdown preview + task checklist **с колонкой/badge assignee**  
- Кнопки: New change, Apply, Archive  
- Apply → modal: self / subagents / hybrid + превью dispatch  
- Badge: N open changes  

**v3 — Gates & review**  
- Diff main vs delta  
- Approve change before apply  
- Link change_id ↔ chat thread / **subagent run per task**  
- Drag-drop reassign assignee перед apply

---

## 9. Поэтапный план внедрения (PR-ы)

### PR1 — Foundation (Helix) ✅

- `core/sdd/`: store, paths, parse tasks checklist **+ assignee**  
- tools: init, list, read, create_change, status, write_artifact, set_task_assignee  
- skill `holix-sdd-propose` (tasks **must** include assignee)  
- unit tests: `tests/test_sdd.py`  
- **DoD:** `openspec/` + change; в `tasks.md` у каждой task есть assignee

### PR2 — Apply loop + execution mode ✅ (tools + skill; auto-dispatch later)

- skill `holix-sdd-apply`  
- **pre-apply ask:** self / subagents / hybrid (`sdd_request_apply_mode` / `sdd_set_apply_mode`)  
- `sdd_apply` блокируется без mode; возвращает plan task→executor  
- `sdd_check_task`  
- **DoD:** без выбранного mode coding plan не выдаётся

### PR2b — Apply via subagents ✅

- `sdd_dispatch` → SubagentManager.spawn_typed по assignee  
- task ↔ job в `.task-jobs.json`  
- mode self: без spawn  

### PR3 — Archive + merge ✅

- delta merge algorithm (ADDED/MODIFIED/REMOVED)  
- `sdd_archive`  
- skill `holix-sdd-archive`  
- tests на merge + full lifecycle  
- **DoD:** после archive main specs обновлены, change в archive/

### PR4 — Studio slash + API ✅

- HTTP `/studio/api/sdd/*`  
- slash `/spec …` (Helix AgentCommands + Studio host)  
- **DoD:** полный цикл из UI/chat  

### PR5 — Specs panel UI ✅

- tab Specs: domains, changes, tasks, apply mode, apply/archive  
- badge open changes  

### PR6 — Policy + polish ✅

- soft gate на `write_file`  
- docs `docs/ru/SDD.md`  
- entitlement `agent.sdd` (default on)  
- OpenSpec CLI interop — deferred

---

## 10. Соответствие OpenSpec ↔ Holix

| OpenSpec | Holix Studio |
|----------|--------------|
| `/opsx:explore` | skill explore / free chat no artifacts |
| `/opsx:propose` | `/spec propose` + `sdd_create_change` + artifacts |
| `/opsx:apply` | `/spec apply` + **ask mode** + implement + `tasks.md` |
| (нет) | `assignee` в tasks → main / subagent types |
| (нет) | pre-apply: self \| subagents \| hybrid |
| `/opsx:archive` | `/spec archive` + merge |
| `openspec status` | `sdd_status` + Specs panel |
| `openspec/specs` | то же дерево в workspace |
| `changes/archive` | то же |
| Node CLI | v1 native Python; v2 optional CLI |
| Custom schemas | v2 `schemas/` |
| Fluid not rigid | soft gates, skip for tiny fixes |

---

## 11. Риски и решения

| Риск | Митигация |
|------|-----------|
| Агент игнорирует specs | Soft gate + skill priority + UI reminder |
| Агент сразу кодит без вопроса mode | Hard stop в `sdd_apply` / skill: mode required |
| Assignee без registry | Propose из актуального registry; reassign на apply |
| Параллельные субагенты ломают одни файлы | design: conflict zones → `main` или serial owner |
| Merge ломает spec.md | Strict section parser + tests + backup before archive |
| Дублирование plan_and_execute | Docs: plan = run; SDD = product truth |
| Раздувание context | В prompt только active change + summary main specs, full read on demand |
| Конфликт с git | Archive = file ops; commit — user/agent explicit |

---

## 12. Метрики успеха

- % feature tasks с change + archive  
- % tasks с заполненным assignee на propose  
- % apply с явным выбором mode (не silent default)  
- Доля apply в mode subagents/hybrid vs self  
- Время от propose → first apply  
- Число open changes > 14 дней (застой)  
- После archive: agent ссылается на main specs в следующем change  

---

## 13. Рекомендация по старту

**Начать с PR1–PR2 в Helix** (lifecycle + assignees + **обязательный ask mode** + self apply), затем **PR2b** (dispatch субагентам), PR3 archive, Studio API/slash, Specs panel.  
Layout **`openspec/`** — чтобы совпадать с форком OpenSpec и при желании подключить CLI.

**Минимальный MVP:**  
init + propose (**tasks + assignee**) + **pre-apply ask (self vs subagents)** + self apply + archive merge + slash `/spec *`.  
Subagent dispatch (PR2b) — сразу после self-path, не откладывать «на потом» если Studio уже имеет Subagents monitor.

---

## 14. Связанные точки в текущем коде

| Область | Где | Заметка |
|---------|-----|---------|
| Plan/execute modes | Helix `core/graph/*`, `plan_and_execute` | Ephemeral plan steps — не durable specs |
| Plan review UI | Studio `plan_review_*`, `PlanReviewGuard` | Approve runtime plan, не OpenSpec artifacts |
| Slash commands | Studio host + `slash_commands`, chat `/…` | Место для `/spec …` |
| Skills | Holix skills manager | Ship SDD skills без полного Node OpenSpec CLI |
| Workspace files | Studio files/git, workspace root | Дом для `openspec/` |
| Subagents | manager + monitor tab | Apply: dispatch по assignee; task ↔ run |
| Plan review UI | может переиспользовать паттерн | Apply mode dialog по аналогии с plan approve |
| Entitlements | control plane features | Flag `agent.sdd` / `specs.panel` (опц.) |

---

## 15. Следующие шаги

1. Design doc + детальный PR plan (артефакты / API / merge / **assignee schema** / apply modes / UI wireframe), **или**  
2. Сразу PR1: scaffold `core/sdd/` + tools + skill propose **с assignee в tasks**.
