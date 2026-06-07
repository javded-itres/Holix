# План рефакторинга Helix

> **Версия:** 1.0  
> **Дата:** June 2026  
> **Ветка:** `feature/subagents`  
> **Статус:** Завершён (фазы 0–8, ветка `refactor/unified-runtime`)

План опирается на архитектуру v0.2 (`docs/architecture.md`) и технический долг, выявленный при анализе кодовой базы. Цель — **один путь выполнения**, **предсказуемые контракты**, **модульный TUI**, **стабильные тесты** без остановки разработки фич.

---

## Принципы

| Принцип | Что это значит на практике |
|---------|----------------------------|
| Strangler Fig | Сначала выносим общий код, потом отключаем legacy |
| Контракты через события | UI/API зависят только от `AgentEvent`, не от LangGraph напрямую |
| Feature flags остаются | Рефакторинг не меняет поведение по умолчанию |
| Тесты как gate | Каждая фаза заканчивается зелёным `pytest` |
| Маленькие PR | 200–400 строк, вертикальные срезы |

---

## Целевая архитектура (после рефакторинга)

```
┌─────────────────────────────────────────────────────────────┐
│  Интерфейсы: TUI (modules) │ CLI │ API Gateway             │
│         └──────────────────┴─────┴── subscribe AgentEventBus
├─────────────────────────────────────────────────────────────┤
│  HelixAgent → run_helix() [единая точка входа]              │
│                    └─→ LangGraph (compiled)                 │
├─────────────────────────────────────────────────────────────┤
│  SessionContext (DI) │ MemoryFacade │ ToolRegistry + Guards │
└─────────────────────────────────────────────────────────────┘
```

**Убираем:** прямой вызов `run_agent_loop` из TUI/chat при `use_langgraph=True`.  
**Оставляем:** `run_agent_loop` только как thin adapter или удаляем после миграции.

---

## Фазы

### Фаза 0 — Стабилизация (1–2 дня, блокер для всего остального)

**Цель:** зелёный CI и чистый репозиторий.

| # | Задача | Детали |
|---|--------|--------|
| 0.1 | Починить `get_conversation` | Сейчас `ORDER BY timestamp DESC` — тест и UI ожидают хронологию. Вариант: `ASC` + `limit` с подзапросом, или явный параметр `order="asc"`. |
| 0.2 | Закоммитить новые пакеты | `core/graph`, `subagents`, `plan_review`, `evolution`, тесты — без `.helix/`, `.langgraph_api/`, `.pid`. |
| 0.3 | Синхронизировать docs | README → v0.2, таблица флагов из `config.py`, команда `helix tui`. |
| 0.4 | Baseline метрик | Зафиксировать: 156 тестов, время прогона, размер `app.py`. |

**Критерий готовности:** `uv run pytest` — 156/156.

---

### Фаза 1 — Унификация execution layer (3–5 дней)

**Проблема:** дублирование между `run_agent_loop` (~540 строк) и `run_graph_loop` (~160+ строк setup): загрузка истории, сохранение user message, context compression, emit events.

| # | Задача | Результат |
|---|--------|-----------|
| 1.1 | `core/runtime/session.py` | `prepare_session(agent, user_input, conversation_id)` — единая подготовка messages + compression + persist. |
| 1.2 | `core/runtime/executor.py` | `async def run_helix(agent, ..., stream, execution_mode) -> AsyncGenerator[AgentEvent]` — единственная публичная точка. |
| 1.3 | Адаптеры | `loop.py` / `loop_streaming.py` / `gateway` / TUI вызывают только `run_helix`. |
| 1.4 | Deprecate legacy loop | `use_langgraph=False` → warning + делегирование в graph (или удаление флага через 1 релиз). |
| 1.5 | Тесты | Перенести `test_agent_events` на `run_helix`; добавить parity-тест: react через graph даёт те же типы событий. |

**Критерий:** нет ветвления `if use_langgraph` в `cli/tui/app.py` и `cli/commands/chat.py`.

```python
# Целевой API (эскиз)
async for event in run_helix(agent, user_input, conv_id, stream=True, mode="auto"):
    bus.emit(event)
```

---

### Фаза 2 — Dependency Injection (2–4 дня) ✅ частично

**Проблема:** `HelixAgent` и узлы графа читают глобальный `settings`; комментарии «Phase 0» в `agent.py`.

| # | Задача | Статус |
|---|--------|--------|
| 2.1 | `HelixRuntimeConfig` dataclass | ✅ `core/di/runtime_config.py` |
| 2.2 | Dishka container + providers | ✅ `core/di/` (dishka>=1.10) |
| 2.3 | `HelixAgent(config=...)` | ✅ без мутации `settings` в CLI/TUI |
| 2.4 | `resolve_runtime_config(profile)` | ✅ profile + ModelManager |
| 2.5 | FastAPI `setup_dishka` | ✅ `api/gateway.py` lifespan |
| 2.6 | Graph nodes → `agent.config` | ✅ plan/finalize/review nodes |

**Осталось:** убрать оставшиеся `settings` в episodic/vector/subagents; optional `FromDishka[HelixAgent]` в gateway handlers.

---

### Фаза 3 — Память: фасад и контракты (3–4 дня) ✅

| # | Задача | Статус |
|---|--------|--------|
| 3.1 | `ConversationStore` | ✅ `core/memory/conversation.py` |
| 3.2 | `LongTermMemoryStore` | ✅ `core/memory/ltm.py` |
| 3.3 | `MemoryFacade` | ✅ `core/memory/facade.py` |
| 3.4 | `ConversationSummarizer` | ✅ `core/memory/summarizer.py` |
| 3.5 | `manager.py` slim exports | ✅ ~15 строк (aliases) |
| 3.6 | Тесты | ✅ `tests/test_memory_facade.py` |

**Контракт:** `get_conversation` → ASC; `search` → relevance order (ChromaDB).

---

### Фаза 4 — Граф: упрощение и связность (4–6 дней) ✅

| # | Задача | Статус |
|---|--------|--------|
| 4.1 | Mode builders | ✅ `modes/react.py`, `plan_execute.py`, `hybrid.py` |
| 4.2 | Routers | ✅ `core/graph/routers.py` |
| 4.3 | Plan parsing | ✅ `core/plan_review/parser.py`; `plan_node.py` ~454 строк |
| 4.4 | Checkpointing | ✅ `create_checkpointer()` в `run_graph_loop` |
| 4.5 | Subagents node | ✅ `delegate_subagent_node` в plan-and-execute graph |
| 4.6 | Slim builder | ✅ `builder.py` ~200 строк, композиция mode builders |

---

### Фаза 5 — TUI: декомпозиция (5–8 дней) 🔄

**Проблема:** `cli/tui/app.py` — ~4178 строк (было 5241), `handlers/` + `widgets/`.

**Целевая структура:**

```
cli/tui/
├── app.py              # HelixApp (~300 строк): compose, bindings, lifecycle
├── screens/
│   └── chat_screen.py
├── widgets/
│   ├── chat_log.py
│   ├── sidebar.py
│   ├── input_area.py
│   ├── subagents_panel.py   # из subagents_widget.py
│   ├── plan_review.py
│   └── confirmation.py
├── handlers/
│   ├── event_handler.py     # AgentEvent → UI updates
│   └── slash_commands.py
└── state/
    └── session_state.py     # streaming buffer, scroll flags
```

| # | Задача | Статус |
|---|--------|--------|
| 5.1 | `AgentEventHandler` | ✅ `cli/tui/handlers/event_handler.py`; `app._on_agent_event` → delegate |
| 5.2 | `SlashCommandHandler` | ✅ `cli/tui/handlers/slash_commands.py` (~286 строк) |
| 5.3 | Widgets | ✅ `HelixSidebar`, `HelixMainContent`, `HelixChatLog`, `HelixInputArea`; CSS → `widgets/styles.py` |
| 5.4 | Modals | ✅ `ModalStack` + confirmation/plan review presenters |
| 5.5 | Agent runner | ✅ TUI streaming через `run_helix` only |

**Критерий:** `app.py` < 500 строк; roadmap TUI Phase 2 (layout tabs) становится выполнимым.

---

### Фаза 6 — Events & observability (2–3 дня) 🔄

**Проблема:** `AgentEventBus` — «Phase 0 callbacks»; TUI и gateway подписываются по-разному.

| # | Задача | Статус |
|---|--------|--------|
| 6.1 | Async queue mode | ✅ `AgentEventBus.subscribe_queue()` |
| 6.2 | Correlation IDs | ✅ `run_id` / `plan_id` на `AgentEvent`; `begin_run` / `stamp_event` |
| 6.3 | Structured logging | ✅ `correlation_fields()` + run_id/plan_id в log extras |
| 6.4 | Metrics | ✅ `events.*`, `tool.{name}`, `confirmation.*`, `plan_review.*` |

---

### Фаза 7 — API & CLI консистентность (2–3 дня) ✅

| # | Задача | Статус |
|---|--------|--------|
| 7.1 | Gateway `agent.run` → `run_helix` | ✅ via `_run_with_graph` / `StreamingAgentLoop` |
| 7.2 | OpenAI error mapping | ✅ `api/errors.py` + chat completions |
| 7.3 | Plan/confirm endpoints | ✅ `/v1/plan/review`, `/v1/confirmations/resolve` |
| 7.4 | CLI без `run_agent_loop` | ✅ `chat`/`run` → `run_helix` или `agent.run` |

---

### Фаза 8 — Качество и инфраструктура ✅

| # | Задача | Статус |
|---|--------|--------|
| 8.1 | `pytest` markers | ✅ `unit` / `integration` / `llm` в `conftest.py` |
| 8.2 | Ruff + mypy | ✅ конфиг в `pyproject.toml` (`uv run ruff check core`) |
| 8.3 | ChromaDB isolation | ✅ `memory_chroma_collection` per test |
| 8.4 | pytest → dev group | ✅ `[dependency-groups] dev` |
| 8.5 | Graph react E2E | ✅ `tests/test_graph_e2e.py` |

---

## Приоритизация

**Рекомендуемый порядок:** 0 → 1 → (2 ∥ 3) → 5 → 4 → 6 → 7 → 8.

Фазы 2 и 3 можно вести параллельно разными PR после фазы 1.

| Фаза | Оценка | Зависимости |
|------|--------|-------------|
| 0 Стабилизация | 1–2 дня | — |
| 1 Execution | 3–5 дней | 0 |
| 2 DI | 2–4 дня | 1 |
| 3 Memory | 3–4 дня | 1 |
| 4 Graph | 4–6 дней | 2 |
| 5 TUI | 5–8 дней | 1 |
| 6 Events | 2–3 дня | 5 |
| 7 API | 2–3 дня | 1 |
| 8 Quality | ongoing | — |

---

## Риски и митигация

| Риск | Митигация |
|------|-----------|
| Регрессия streaming | Parity-тесты событий + ручной чеклист TUI `/stream on` |
| Поломка plan review | Не трогать `PlanReviewGuard` API; только перенос вызовов |
| Subagents в процессах | Рефакторить после стабилизации execution; не менять IPC протокол |
| Долгий TUI split | Выносить по одному handler за PR |

---

## Метрики успеха (Definition of Done)

| Метрика | Сейчас | Цель |
|---------|--------|------|
| Тесты | 155/156 | 156+ |
| Точек входа execution | 2+ | 1 (`run_helix`) |
| `app.py` строк | 5241 | < 500 |
| `settings` в graph nodes | много | 0 |
| `use_langgraph` ветвления в UI | есть | 0 |
| README vs architecture | расхождение | синхрон |

---

## Что сознательно не трогаем

- Смена LLM SDK (остаётся OpenAI-compatible client).
- Добавление LangChain chains (в architecture явно исключено).
- Включение по умолчанию subagents / evolution / meta-agent.
- Полный rewrite skills/ChromaDB.

---

## Первые три PR (конкретный старт)

1. **PR-1:** Fix `get_conversation` ordering + тест + `.gitignore` для `.helix/`.
2. **PR-2:** `prepare_session` + `run_helix`; TUI/chat/gateway на новый API; deprecate ветку в TUI.
3. **PR-3:** Вынести `EventHandler` из `app.py` (~1200 строк), без изменения UX.

---

## После рефакторинга: браузерные инструменты

На ветке `refactor/unified-runtime` добавлена опциональная автоматизация через Playwright (не входила в фазы 0–8 плана, но использует тот же `ToolRegistry` + `ActionGuard` + `conversation_id`).

| Компонент | Путь |
|-----------|------|
| Сессии | `core/tools/browser/session.py` |
| Инструменты | `core/tools/browser/tools.py` |
| URL policy | `core/tools/browser/policy.py` |
| Документация | [guides/BROWSER_TOOLS.md](./guides/BROWSER_TOOLS.md) |

Включение: `ENABLE_BROWSER_TOOLS=true`, `uv sync --extra browser`, `playwright install chromium`.

---

## Связанные документы

- [architecture.md](./architecture.md) — текущая архитектура v0.2
- [guides/BROWSER_TOOLS.md](./guides/BROWSER_TOOLS.md) — Playwright browser tools
- [roadmap/TUI.md](./roadmap/TUI.md) — roadmap Textual TUI
- [CLAUDE.md](../CLAUDE.md) — обзор проекта для разработчиков