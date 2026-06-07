# Helix TUI (strict / code style)

`helix tui` запускает **одноколоночный** интерфейс в духе Claude Code и Grok Build: транскрипт, компактные tool-блоки, строка статуса, поле ввода. Без сайдбара и Command Palette (Ctrl+P).

## Запуск

```bash
helix tui
helix tui --profile myprofile
```

### Legacy dashboard (временный откат)

```bash
HELIX_TUI_LEGACY=1 helix tui
```

Старый UI с сайдбаром, Ctrl+P и collapsible-панелями лежит в `cli/tui/legacy/`.

## Layout

```
┌─────────────────────────────────────────────┐
│ transcript (scroll)                         │
│  ❯ user message                             │
│  ⎿ tool_name ✓ (0.4s)                       │
│     assistant markdown…                     │
├─────────────────────────────────────────────┤
│ · thinking…          (одна строка, in-place)│
├─────────────────────────────────────────────┤
│ profile · model · cwd · mode · session · ctx│
├─────────────────────────────────────────────┤
│ prompt (multiline)                          │
└─────────────────────────────────────────────┘
```

## Клавиши

| Клавиша | Действие |
|---------|----------|
| Enter | Отправить |
| Shift+Enter | Новая строка |
| Ctrl+L | Очистить транскрипт |
| Ctrl+End | Вниз транскрипта |
| Shift+Tab | Режим: react → plan → hybrid → auto |
| Ctrl+S | Остановить workers |
| F1 | Справка |
| F2 | Полный транскрипт (выделение и копирование) |
| Ctrl+Shift+C | Копировать выделение, иначе последний ответ, иначе tool |
| Tab (в `/…`) | Автодополнение слэш-команд |

### macOS и русская раскладка

На **macOS** с раскладкой **Русская**:

- Символ `/` обычно набирается как **Shift+7**; клавиша на месте US `/` даёт **`,`** или **`.`**.
- Слэш-команды принимают алиасы: `,help`, `.clear`, `?copy` → то же, что `/help`, `/clear`, `/copy`.
- Tab-дополнение нормализует префикс в `/…`.
- Дополнительный скролл транскрипта: **⌃↑** / **⌃↓** / **⌃PgUp** / **⌃PgDn** / **⌃Home** (надёжнее, чем Page Up/Down в терминале).

Модификаторы в справке (F1) показываются как **⌃** / **⇧** на macOS.

### Копирование текста

RichLog в терминале не всегда даёт удобное выделение мышью. Поэтому параллельно ведётся **plain-text store** (`cli/tui/shared/transcript_store.py`):

1. **Клик по транскрипту** → выделение мышью → кнопка **Copy** справа сверху (или горячая клавиша).
2. **Ctrl+Shift+C** — выделение на экране, иначе последний ответ ассистента, иначе последний tool.
3. **F2** или **`/open`** — модальное окно с read-only `TextArea` (удобно выделить всё и скопировать).
4. **`/copy`**, **`/copy tool`**, **`/copy all`** — в буфер обмена без выделения.

На **macOS** в TUI: выход — **⌃Q**. Копирование:

| Терминал | Горячая клавиша |
|----------|-----------------|
| **iTerm2** | **⌘C** (доходит в приложение) |
| **Terminal.app** | **⌃C** или **⌃⇧C** — ⌘C остаётся у Terminal и в Helix не приходит |
| любой | F2, `/copy`, `/copy all` |

В **Terminal.app** выделение + **⌘C** копирует только через буфер macOS (без Helix store); для последнего ответа агента используйте **⌃C** или `/copy`.

Фокус на поле ввода не возвращается автоматически, пока фокус на `#transcript` (можно спокойно выделять текст).

## Слэш-команды (core+)

| Команда | Описание |
|---------|----------|
| `/help` | Справка |
| `/clear` | Очистить чат |
| `/stream` | Вкл/выкл streaming |
| `/mode` | Сменить execution mode |
| `/metrics` | Метрики |
| `/stop` | Остановить задачи |
| `/new` | Новая сессия |
| `/sessions` | Список сессий |
| `/switch N` | Переключить сессию |
| `/session name X` | Имя текущей сессии |
| `/profile [name\|N]` | Профиль |
| `/memory <q>` | Поиск по памяти (в транскрипт) |
| `/last`, `/tools` | Вывод инструментов |
| `/copy`, `/copy tool`, `/copy all` | Копирование в буфер |
| `/open` | Просмотр полного транскрипта |
| `/yes`, `/no`, `/1`–`/4` | Подтверждения |
| `/plan-*` | Plan review |

Подтверждения и plan review по-прежнему используют модальные окна (`cli/tui/modals/`).

## Состояние

`~/.helix/tui-state.json`:

```json
{
  "conversation_id": "tui_default_…",
  "streaming_enabled": false,
  "execution_mode": "react"
}
```

## Архитектура

| Путь | Роль |
|------|------|
| `cli/tui/code/app.py` | `HelixCodeApp` |
| `cli/tui/code/handlers/events.py` | События агента → транскрипт |
| `cli/tui/code/handlers/slash.py` | Слэш-команды |
| `cli/tui/shared/formatters.py` | Форматирование tool-строк |
| `cli/tui/shared/transcript_store.py` | Plain-text для /copy и F2 |
| `cli/tui/modals/transcript_viewer.py` | Модальный просмотр транскрипта |
| `cli/tui/legacy/` | Прежний dashboard TUI |

События агента: `core/agent_events.py`, выполнение: `run_helix()`.

## Миграция с dashboard TUI

- Сайдбар Tools/Memory/Sessions → `/tools`, `/memory`, `/sessions`, `/switch`
- Ctrl+P → `/help` и слэш-команды
- `/density`, `/reset-ui` — только в legacy UI
- Плотность интерфейса фиксирована (compact)

## Тесты

```bash
uv run pytest tests/test_tui_code_handlers.py tests/test_transcript_store.py -q
```

## Связанные документы

- [roadmap/TUI.md](../roadmap/TUI.md)
- [BROWSER_TOOLS.md](BROWSER_TOOLS.md)