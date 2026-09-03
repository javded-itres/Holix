# Code mode

Opt-in способ показать модели инструменты: она пишет **Python-программу**, которая вызывает tools Holix, а не по одному JSON-вызову на шаг ReAct.

По умолчанию — **native**. Для Telegram `main` оставляйте `native`, пока не включите слот `coder`.

Ключи конфига — в [CONFIGURATION.md](CONFIGURATION.md#code-mode-opt-in). Меню мессенджеров — в [SUBAGENTS.md](SUBAGENTS.md#telegram-и-max). Эта страница — поведение `run_code`.

## Когда включать

| Режим | На проводе | Зачем |
|-------|------------|-------|
| `native` | Обычные схемы tools | По умолчанию. Чат, Telegram `main`. |
| `code` | Только `run_code` + SDK в system prompt | Много файлов, много чтений за шаг. |
| `both` | Схемы **и** `run_code` | Эксперименты; промпт больше. |

## Включение

`~/.holix/profiles/<name>/config.yaml`:

```yaml
tools_presentation: code   # native | code | both
```

По слоту (Telegram `main` остаётся native, `coder` — code):

```yaml
tools_presentation: native
tools_presentation_by_slot:
  coder: code
```

Капы (необязательно):

```yaml
code_mode_wall_timeout_s: 120
code_mode_max_inner_calls: 40
code_mode_parallel_readonly: true
```

Те же ключи можно переключать из TUI и Telegram/MAX — [SUBAGENTS.md](SUBAGENTS.md#telegram-и-max).

## Что пишет модель

```python
hits = tools.grep(pattern="TODO", path=".")
return {"n": len(hits)}
```

- Имя `tools` уже в области видимости. `import tools` / `from tools import …` — тот же объект.
- У `run_code` обязательны `code` (тело функции) и `description`.
- В контекст возвращаются только `print()` и `return`. Внутренние дампы обрезаются.
- Относительные пути и `run_terminal_command` стартуют в `workspace_root` профиля, не в cwd процесса.
- Сервер: `tools.start_background_process(...)`, не `run_terminal_command`.
- Правки существующих файлов: `tools.patch_file(...)` (Claude/Qwen/DeepSeek) или `tools.apply_patch(patch=...)` (GPT/Codex). `write_file` — новый файл или полная перезапись. См. [TOOLS.md](TOOLS.md).
- Локальный HTTP проверяйте `curl` через `run_terminal_command`. `fetch_url` localhost отклоняет.
- Не импортируйте `os`, `subprocess`, `pathlib`. Файлы и shell — через `tools.*`.

## Безопасность

Программа в изолированном **subprocess** (`python -I`), как `execute_python`. Каждый `tools.name(...)` идёт через `ToolRegistry`: ActionGuard, jail, allow-list. Запись в файлы — с подтверждением.

Внутри программы нельзя: `run_code`, `execute_python`, `ask_user`, `external_cli`, `run_acp_agent`, `delegate_to_subagent`, `research_site_pages`, cron, browser-tools. `todo_write` разрешён.

В TUI и Telegram/MAX — **свёрнутая карточка**: `description` и имена внутренних tools, без тела программы.

## Лимиты (v1)

- Изменяющие вызовы строго по очереди. Read-only (`risk_level: no`) — `tools.parallel(...)`.
- Wall-timeout (по умолчанию 120 с) и лимит внутренних вызовов (40).
- Новый воркер на каждый `run_code` (не REPL).
- Редирект `>/dev/null` разрешён; `/dev/tcp` и сырые диски — нет.
