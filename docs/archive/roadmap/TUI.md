# Roadmap: Helix Textual TUI (Textual User Interface)

> **Июнь 2026:** `helix tui` по умолчанию — **strict code UI** ([guides/TUI.md](../guides/TUI.md)). Dashboard с сайдбаром и Ctrl+P: `HELIX_TUI_LEGACY=1` → `cli/tui/legacy/`.

## Vision

Создать современный, удобный и продуктивный **полноэкранный терминалный интерфейс** для агента Helix, который будет значительно превосходить текущий линейный REPL по удобству работы с длинными сессиями, инструментами и контекстом.

TUI должен:
- Хорошо работать с большими объёмами вывода инструментов
- Давать хорошую видимость происходящего (thinking, tool calls, streaming)
- Поддерживать эффективную навигацию по истории
- Быть стабильным и приятным в ежедневном использовании (особенно на macOS)

---

## Текущая Архитектурная Основа (Phase 0 — Foundation)

Перед созданием TUI была проведена важная подготовительная работа:

- **AgentEvent система** (`core/agent_events.py`)
  - Типизированные события (`ThinkingEvent`, `ToolCallStartEvent`, `AssistantDeltaEvent`, `FinalResponseEvent` и др.)
  - `AgentEventBus` с поддержкой синхронных и асинхронных подписчиков
  - Гибридная модель (сейчас callbacks, с заделом под `asyncio.Queue`)

- **Унифицированный движок выполнения** (`core/agent_execution.py`)
  - Единая функция `run_agent_loop(...)` с поддержкой `stream=True/False`
  - Устранено сильное дублирование между `loop.py` и `loop_streaming.py`

- **Интеграция мониторинга**
  - `monitoring.logger` и `monitoring.metrics` подписаны на события агента

- **Улучшенная работа с моделями**
  - `ModelManager` теперь используется и в TUI (раньше модель бралась напрямую из профиля)

**Статус Phase 0**: В основном завершена.

---

## Phase 1: Минимальный Рабочий PoC TUI (Текущий статус — Продвинутый)

**Цель**: Создать отдельную команду `helix tui`, которая уже полезна в повседневной работе.

### Что уже реализовано (на момент написания)

- Отдельная команда `helix tui` (регистрируется в `cli/main.py`)
- Базовый layout:
  - Sidebar (Profile, Model, Status, кнопка Clear)
  - Основная область чата (`RichLog`)
  - Поле ввода (`TextArea` с поддержкой многострочности)
- Реактивное обновление UI через `AgentEvent`:
  - Thinking
  - Tool calls с красивыми панелями (с аргументами и результатами)
  - Live streaming токенов (`AssistantDeltaEvent`)
- Поддержка streaming-режима (`/stream on/off`)
- Слэш-команды внутри TUI (`/clear`, `/metrics`, `/stream`, `/help` и др.)
- Улучшенная навигация по истории:
  - Клавиатурный скролл (в т.ч. macOS-friendly комбинации с Ctrl)
  - Умный auto-scroll (отключается при ручном скролле вверх)
- Загрузка истории предыдущего разговора при старте
- Обработка ошибок (TUI не падает при ошибках агента)
- Поддержка Markdown на финальном ответе
- Enter = отправить, Shift+Enter = новая строка

**Статус**: Phase 1 находится в продвинутой стадии. Базовый рабочий PoC уже существует и активно используется.

---

## Вариант 1: Стабилизация и Полировка Текущего PoC (Текущий Фокус)

Пользователь выбрал этот вариант как приоритетный перед переходом к Phase 2.

### Приоритетные направления стабилизации

| Приоритет | Задача | Статус | Комментарий |
|---------|--------|--------|-----------|
| Высокий | Надёжная обработка ошибок (TUI не должен падать) | В процессе | Добавлены широкие `try/except` в обработчиках событий и запуске агента |
| Высокий | Улучшение работы с длинными результатами инструментов | В процессе | Сейчас обрезается + подсказка про `/memory`. Хочется collapsible/лучший UX |
| Высокий | Качественный скролл истории (в т.ч. на macOS) | Значительно улучшен | Добавлены Ctrl-комбинации + явные mouse scroll handlers + auto-scroll флаг |
| Средний | Улучшение визуала и удобства | В процессе | Статус в сайдбаре + хедере, авто-прокрутка, фокус |
| Средний | Загрузка и отображение истории сообщений | Реализовано | При старте загружается недавняя история из памяти |
| Средний | Качественный streaming + Markdown | Улучшен | Буфер + рендер Markdown на финальном событии |
| Низкий | Сохранение истории между перезапусками TUI | Не начато | Сейчас история живёт только внутри одной сессии TUI |

### Известные проблемы / области для полировки (на момент написания)

- Прокрутка тачпадом/мышкой на macOS работает нестабильно (зависит от терминала)
- При очень длинных результатах инструментов интерфейс может быть неудобным
- Отсутствует визуальный индикатор "ты отскроллил вверх, есть новые сообщения"
- Нет удобного способа посмотреть полный вывод предыдущего инструмента

---

## Phase 2: Расширенный TUI (Начато)

**Статус (апрель 2026)**: Переход из Phase 1 (минимальные виджеты + стабилизация) → Phase 2.

**Первая серьёзная фича Phase 2**:
- **Collapsible + улучшенная визуализация tool calls** — завершено в хорошем состоянии:
  - Start + Result/Error группируются в один Collapsible по `tool_id`
  - Успешные результаты автоматически сворачиваются
  - Ошибки раскрыты
  - Улучшенные заголовки с длительностью
  - Очистка состояния при clear/new session

### Возможные направления Phase 2

- **Боковые панели и мульти-панельный интерфейс**
  - Список доступных навыков с поиском
  - Поиск по памяти прямо в интерфейсе
  - История предыдущих разговоров / переключение сессий

- **Улучшенная работа с инструментами**
  - Collapsible блоки с результатами инструментов
  - Возможность повторно запустить инструмент
  - Лучшая визуализация параллельных/длинных tool calls

- **Профили и переключение контекста**
  - Переключение профиля внутри TUI (начато: `/profile`, Command Palette, `_switch_profile`)
  - Видимые различия между профилями

- **Командная палитра и расширенные слэш-команды**
  - `/` с автодополнением
  - Быстрый доступ к часто используемым действиям

- **Темы и кастомизация**
  - Несколько цветовых схем
  - Настройка плотности интерфейса

---

## Phase 3: Продвинутый / Power-User TUI

- Многооконность / сплиты
- Визуализация работы нескольких агентов / sub-agents
- Отладочный режим (просмотр полного контекста, промптов, tool schemas)
- Интеграция с внешними инструментами (git, редакторы и т.д.)
- Плагинная система для кастомных виджетов
- Удалённый режим работы (TUI как клиент к удалённому агенту)

---

## Текущие Приоритеты (Рекомендация)

**Вариант 1 (Стабилизация и Полировка)** — в основном завершён (апрель 2026):

- Скролл + визуальная индикация (включая macOS)
- Работа с длинными результатами инструментов (`/last`, `/tools`)
- Надёжный фокус ввода
- Высокая устойчивость к ошибкам (глобальный `on_error`, защита всех ключевых путей)

### Следующий слой Phase 1 (текущий фокус)

После стабилизации переходим к добавлению **минимально необходимых полезных виджетов** внутри Phase 1:

1. **Available Tools** в сайдбаре — реализовано
2. **Memory** — компактный список недавних записей + команда `/memory <query>` для семантического поиска — реализовано
3. **Сессии** — визуальный список в сайдбаре (ListView) + команды `/new`, `/sessions`, `/switch N` — UI доведён
4. **Улучшено отображение Tools** — динамический счётчик, короткие описания в списке, лучшая компактность
5. Полировка Memory + авто-обновление списков

Только после этого имеет смысл переходить к Phase 2 (полноценные боковые панели, skills browser, мульти-сессии и т.д.).

---

## Связанные Документы

- `docs/reference/SUMMARY.md` — общая архитектура проекта
- `cli/tui/app.py` — текущая реализация TUI (с пометками Phase 1 PoC)
- `core/agent_events.py` и `core/agent_execution.py` — фундамент событийной архитектуры

---

*Документ создан на основе истории разработки и текущего состояния кодовой базы (апрель 2026).*

## Recent Phase 2 Progress (autonomous continuation)

**Completed items (each followed by commit per request):**

- **Advanced memory search UI in sidebar**  
  `/memory <q>` now populates the Memory ListView with semantic results (distinct "[S]" mode, dynamic Collapsible title). Click any result to insert full content. `/memory-clear` + palette action to return to recent msgs. Auto-reset on new/clear/profile switch.

- **Persistence of density + Collapsible states**  
  `~/.helix/tui-state.json` stores chosen density and which of the 5 sidebar sections (Tools/Memory/...) are collapsed. Restored on every `helix tui` launch. `/reset-ui` (and palette) to wipe. Changes auto-saved via toggle events + density apply.

- **Dynamic contextual hits in Command Palette (Ctrl+P)**  
  In addition to static actions, palette now offers live "Insert memory [1/2/3]..." and "Insert last tool output..." based on current session state. Appear contextually on relevant queries. Refactored insert logic for reuse.

- **Dynamic recent sessions quick-switch in palette + Sessions sidebar polish**  
  Ctrl+P + "switch"/"session" now shows direct "Switch to session: xxx (N msgs)" hits. Stronger current marker + live count in the Collapsible title. Dead label code cleaned.

- **Sidebar visibility persistence (finishing touch)**  
  The same tui-state.json now also remembers whether you left the sidebar open or closed (Ctrl+B choice survives restarts). Default closed only for new users / after reset. The full "density + sections + sidebar" customization now feels persistent and personal.

- **Skills sidebar + dynamic palette (Describe / Insert as context)**  
  Full treatment: dynamic "Skills (N)" title, tags in labels, "Describe skill..." and "Insert skill as context" hits from Ctrl+P. Shared helpers with sidebar clicks.

- **Profiles sidebar + dynamic palette profile switching**  
  "Switch to profile: xxx (recent)" hits in Ctrl+P (safe confirmation flow preserved). Dynamic title + strong current marker on the list. Dead label code cleaned.

This completes the major Phase 2 goal: **every important sidebar section now has excellent mouse + full keyboard power-user support via Command Palette**, plus complete persistence of all customization (density, collapsed sections, sidebar visibility).

- **Richer tool call visualization**  
  Tool Start/Result/Error now use structured Rich Panels with colored borders, always-visible duration, smart JSON/Python syntax highlighting via Rich Syntax, and better truncation. /last and /rerun continue to work great.

All changes in `cli/tui/app.py`. The main Phase 2 sidebar + palette + visualization + persistence goals are in very good shape. Outstanding: deeper Command Palette organization (categories), more advanced tool UX, or additional theming.

Next autonomous direction if you say "Продолжай": deeper palette categories or further tool polish.

---

## Latest autonomous Phase 2 polish continuation (post empty-states / focus-return)

**Completed in strict "commit after every item" autonomous loop:**

- **Code hygiene from RichLog revert era**  
  Cleaned stale references in module docstring, comments, and type annotations (`_is_chat_at_bottom`, `_load_conversation_history`, etc.) that still mentioned the experimental TextArea-for-history attempt. Prevents future confusion.

- **Strong keyboard focus visuals + compact contrast**  
  Added explicit `:focus` / `:focus-within` CSS rules for `#input-area` (thick accent border + boost) and all five sidebar ListViews. When lists receive keyboard focus, their border and highlighted items become significantly more prominent (bold + stronger accent).  
  In `.density-compact`, base list item text now uses less aggressive styling by default and lifts fully on focus-within — addresses readability complaints in the densest mode.

- **Previous items in this autonomous stretch (for context)**  
  - Empty state messages improved across all sidebar sections and initial chat log.  
  - Guaranteed input focus return after Command Palette closes (and after most other actions).  
  - Density indicator, session last-activity timestamps + rename, persistence of everything.

All work remains in `cli/tui/app.py` + `docs/roadmap/TUI.md`. The TUI is now in an excellent "daily driver" state for Phase 2: stable, customizable, keyboard-powerful, with clear visual feedback everywhere.

Outstanding (if more "Продолжай"): advanced tool result actions from history, richer palette grouping, or final edge-case robustness passes.

---

## Autonomous continuation — Wave 2 + Wave 3 (latest)

**Completed after "Продолжай" (strict commit-after-each rule):**

**Wave 2**
- Persistent rich status in Header bar: `profile • model • session [density]` — always visible even when sidebar is closed (the default).
- Cleaner, modern first-run welcome text focused on Ctrl+P, density modes, and sessions.
- Two powerful new palette actions: **Copy last tool result** + **Copy last assistant response** (using Textual's `copy_to_clipboard`).
- Refreshed internal `/help` documenting Phase 2 polish (focus states, compact contrast, header status, new copy commands).
- Repo hygiene (removed stray `.bak`).

**Wave 3 (current)**
- **"Insert last Helix response as context"** — full action + static + dynamic palette hits (symmetric counterpart to the new copy action and existing memory/tool inserts). Extremely useful for iterative work in long sessions.
- Live thinking/streaming feedback polish: consistent `⟳` spinner in chat + status/header. Header automatically drops "Thinking..." state the moment the first real tokens arrive.
- All changes remain minimal, robust, and keyboard-first.

The TUI has reached a very high level of daily-driver polish for a Phase 2 PoC while staying true to the original minimal-widget vision.

---

## Latest autonomous continuation (Wave 4 + Wave 5)

**Wave 4**
- **Regenerate last response** — first-class palette action + dynamic hits + slash `/regenerate`. Re-sends your last user message for a fresh answer.
- Consistent rich Panel rendering for all tool result views (`/last`, palette "Show last tool result").
- Improved discoverability: better unknown-command message, added `/regenerate` and `/session-info`.
- Dynamic palette support for session info.
- Defensive state resets on profile switch and clear/new.

**Wave 5 (current "Продолжай")**
- Regenerate now properly refreshes memory sidebar immediately and clears stale streaming buffers.
- Live streaming UX: header shows "**Streaming...**" while deltas are arriving (with proper cleanup on finish/error).
- Long session robustness: `RichLog(max_lines=600)` — soft auto-trim to keep the TUI responsive even after hundreds of messages.
- `/help` updated with a dedicated section for the newest power-user commands (Regenerate, Insert last assistant, Copy actions, Session info).

All changes are small, defensive, and follow the established patterns. The TUI is now significantly more pleasant for extended daily use.

**Wave 6 (latest continuation)**
- Dynamic Command Palette now offers **Insert tool result [1/2/3] as context** for the most recent tool calls (not just the last one) — excellent for chaining context in complex tasks.
- Visual marker `[regenerated]` on responses that came from the Regenerate action (improves history readability when using the feature repeatedly).
- Slash command improvements: `/insert-assistant`, `/insert-tool`, better coverage in the / dropdown.
- Additional defensive resets for transient state (regeneration marker, streaming flags) on manual input and various reset paths.

The PoC has reached an extremely capable state for a keyboard-first terminal interface. Core vision of Phase 2 is complete.

**Wave 7 (current continuation)**
- **Edit Last Message** — powerful companion to Regenerate. Palette action + `/edit-last` prefills the input with your previous message for easy modification and resend.
- Smart "Recent power actions" dynamic section in Ctrl+P (Edit last, Regenerate, Insert last assistant appear automatically for broad/recent queries).
- Improved `/tools` output and hints to better reflect the rich set of modern actions available.
- Extra defensive state resets after Edit/Regenerate flows.
- This wave further strengthens the power-user experience while keeping everything lightweight and keyboard-first.

**Wave 8 (A + B + Enter fix on macOS)**
- **A (Tools depth)**: Structured viewing of tool results — full /last and Show now auto pretty-prints JSON with Syntax highlighting (monokai) for complex structured outputs.
- **B (Light Phase 3 debug)**: New Debug ▸ palette category with "Show Conversation Context", "Show Loaded Tools", "Show Loaded Skills" using agent introspection methods.
- **Enter in dropdowns/palette fix experiment (macOS/OpenCode)**: Removed the global `enter` binding (was conflicting with ListView/OptionList Enter selection in slash suggestions and Command Palette). Now relies purely on focused on_key handling + widget defaults. This should make ↑↓ + Enter selection reliable in all menus without accidentally sending chat messages. All bindings remain Ctrl+ based to match macOS-friendly OpenCode-style (avoids Cmd key theft by terminal/OS). Further tweaks possible based on testing.

The TUI continues to mature as a production-grade daily driver. Phase 2+ is solid; light debugging and better tool history UX added. Key handling improved for macOS reliability.


