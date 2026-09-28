# Слэш-команды (`/`)

Команды с `/` управляют сессией без отправки текста в LLM. Работают в **TUI** (`holix tui`), **Telegram** и частично в **`holix chat-command`**.

Источник: `cli/shared/commands/registry.py`, `cli/shared/commands/agent_commands.py`.

## Поддержка по интерфейсам

| Группа | TUI | Telegram | chat-command |
|--------|-----|----------|--------------|
| Сессии (`/new`, `/switch`) | Да | Да | Нет |
| Копирование (`/copy`, `/open`) | Да | Частично | Нет |
| План (`/plan confirm|auto|refine|reject`) | Да | Да | Нет |
| Подтверждения (`/yes`, `/1`–`/4`) | Да | Да | Нет |
| Hub / MCP | Да | Частично | Нет |
| `/model`, `/skills`, `/memory` | Да | Да | Да (часть) |
| `/compress` | Да | Да | Да |
| `/debug` | Нет | Нет | Да (`chat-command`) |

### Раскладка macOS (RU)

`,help` и `.help` приводятся к `/help`. Символ `/` — **Shift+7**.

---

## Справка и статус

| Команда | Алиасы | Описание |
|---------|--------|----------|
| `/help` | `/h`, `/?` | Справка (Telegram/MAX: меню сценариев; `/help субагенты`). TUI: список команд |
| `/init` | — | Записать/обновить `.holix/HOLIX.md`. В чате фразы «инициализацию Holix» / `HOLIX.md` идут тем же путём |
| `/status` | — | Профиль, режим, сессия |
| `/metrics` | — | Метрики агента |
| `/clear` | `/cls` | Очистить транскрипт |

---

## Модели и выполнение

| Команда | Описание |
|---------|----------|
| `/models` | Выбор модели. `/model` по-прежнему работает. TUI: список провайдера, `r` обновить, `d` модель по умолчанию. Telegram/MAX: ↻ Список и «Нажатие: по умолчанию». `holix chat`: `/model refresh`, `/model default <провайдер> <модель>` |
| `/mode` | Цикл режимов или `/mode <имя>` — см. [EXECUTION_MODES.md](EXECUTION_MODES.md) |
| `/stream` | Стриминг; `/stream on\|off` |
| `/stop` | Остановить агента, субагентов, ожидающие подтверждения и ревью плана (TUI, Telegram, MAX) |
| `/process` | Список фоновых процессов (**TUI**; живые строки ещё и **сверху**) |
| `/process stop` | Остановить dev-сервер / долгий фоновый процесс (**TUI**). `/process-stop` тоже работает |
| `/todos` | Чеклист сессии из `todo_write` (TUI, Telegram, MAX) |
| `/permission` | Показать или задать пресет OS-песочницы: `workspace-write`, `read-only`, `danger-full-access` |
| `/pty` | Постоянный shell сессии: `/pty on\|off\|reset` (POSIX) |
| `/change` | SDD git worktree: список, `/change switch <id>`, `/change leave` |

---

## Сессии (TUI / Telegram)

| Команда | Описание |
|---------|----------|
| `/new` | Новая сессия |
| `/sessions` | Список сессий |
| `/switch N` | Переключиться на №N |
| `/session name <текст>` | Переименовать сессию |
| `/profile` | Список профилей |
| `/profile <имя>` | Сменить профиль |
| `/profile N` | Сменить по номеру |

---

## Память и инструменты

| Команда | Описание |
|---------|----------|
| `/memory <запрос>` | Семантический поиск в памяти |
| `/memory clear` | Сброс UI поиска. `/memory-clear` тоже работает. Стереть память сессии — `/forget` |
| `/last`, `/last N` | Полный вывод инструмента |
| `/tools` | Недавние результаты tools |
| `/trace` | Траектория сессии (tools / модель). `/trace 80` или `/trace search grep` |

---

## Копирование (TUI)

| Команда | Описание |
|---------|----------|
| `/copy`, `/copy last` | Последний ответ ассистента |
| `/copy tool` | Вывод последнего tool |
| `/copy all` | Весь транскрипт |
| `/open`, `/view` | Окно транскрипта (F2) |

---

## Подтверждение рискованных действий

| Команда | Значение |
|---------|----------|
| `/yes`, `/1` | Разрешить один раз |
| `/2` | На сессию |
| `/3` | Всегда |
| `/no`, `/4` | Отклонить |

---

## Согласование плана

| Команда | Действие |
|---------|----------|
| `/plan confirm` | Подтвердить шаг. `/plan-confirm` тоже работает |
| `/plan auto` | Автовыполнение плана |
| `/plan refine` | Уточнить план |
| `/plan reject` | Отклонить |

---

## MCP

| Команда | Описание |
|---------|----------|
| `/mcp` | Меню. Подкоманды: `list`, `install`, `add`, `assign`, `test`, `tools`, `remove` |

CLI: `holix mcp …` — [CLI.md](CLI.md).

---

## Skill Hub

| Команда | Описание |
|---------|----------|
| `/hub` | Каталог. Подкоманды: `installed` (`list` тоже работает), `browse`, `clawhub`, `hermes`, `claude`, `skills-sh` |
| `/plugins`, `/marketplace` | То же, что hub |
| `/skills` | Подсказка: `holix skills list --agent …`. Ещё `pending`, `quality`, `curator` |

CLI: [HUB.md](HUB.md).

---

## Динамические команды навыков

Файл: `{profile}/data/skills/skill-slash.json`
Обновление: `holix hub slash-sync`

---

## Только `chat-command`

| Команда | Описание |
|---------|----------|
| `/exit`, `/quit`, `/q` | Выход |
| `/debug`, `/debug events [N]` | События агента |
| `/compress` | Сжатие контекста в БД |

---

## Cron (периодические задачи)

Нужен запущенный gateway. Полный гайд: [CRON.md](CRON.md).

| Команда | Описание |
|---------|----------|
| `/cron` | Список задач (модал TUI / inline в Telegram). Подкоманды: `list`, `add <расписание> :: <задача>`, `enable`, `disable`, `remove`, `bind` |

**Автосоздание (0.1.16+):** повторяющиеся запросы обычным языком (например «каждый день в 10 утра присылай новости») создают задачу без `/cron add`. CLI: `holix cron …` — [CLI.md](CLI.md#holix-cron).

---

## Субагенты и Code mode

Полный гайд: [SUBAGENTS.md](SUBAGENTS.md). Code mode: [CODE_MODE.md](CODE_MODE.md).

| Команда | Где | Описание |
|---------|-----|----------|
| `/subagents` | TUI, Telegram, MAX | Живые джобы. Подкоманды: `types`, `spawn [--fork] <тип> <задача>`, `result <job>`, `stop <job>`, `reply <job> <текст>`. Старые `/subagent-spawn`, `/subagent-terminate`, `/subagent-types` тоже работают |

В TUI, пока агент занят, обычная строка чата ставится в очередь (эти слэши — нет). См. [TUI.md](TUI.md#очередь-промптов).

## Telegram

```bash
holix telegram sync-menu
```

[TELEGRAM.md](TELEGRAM.md)
