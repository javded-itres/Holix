# Инструменты coding-агента

Holix не копирует зоопарк из 27 tools. Новые имена ниже — полезная часть Claude Code, Codex и DeepSeek Harness. Все они идут через тот же `BaseTool`, реестр, ActionGuard и workspace jail, что `patch_file` / `grep`.

## Правки файлов: `patch_file` vs `apply_patch`

| Семейство моделей | Что вызывать |
|-------------------|--------------|
| Claude, Qwen, DeepSeek | `patch_file` — точный уникальный `old_string` → `new_string` (или `replacements=[…]`) |
| GPT / Codex | `apply_patch` — документ Codex (`*** Begin Patch` … `*** End Patch`) |

`write_file` — только создать файл или полностью заменить. Поиск — `grep` / `glob`, не `rg` / `find` в шелле. Если команда выглядит как `apply_patch <<'EOF' …`, Holix не исполняет шелл, а направляет в tool `apply_patch`.

`apply_patch` атомарный: любой hunk без точного уникального совпадения валит весь вызов (`code: hunk_mismatch`) и ничего не пишет. `dry_run=true` возвращает diff без записи на диск.

## Вопросы: `ask_user`

Доступен **во всех** слотах (main и субагенты). Параметр `questions` (1–5). У вопроса могут быть кнопки (до 8), `multi_select` и `allow_free_text`.

Старый вызов `question` + `context` работает (оборачивается в `questions[0]`). Цикл агента ждёт ответа или таймаута подтверждения (`code: timeout`).

TUI: модалка с кнопками и полем ввода. Telegram / MAX: inline-кнопки. Свободный текст — ответом на сообщение с вопросом.

## Джобы и субагенты

- `job_monitor` — `list` / `tail` / `wait` / `kill` для процессов `start_background_process`. Для tail/wait/kill нужен `job_id`.
- `subagent_control` — `list` / `status` / `send` / `interrupt` / `collect` для **уже запущенных** субагентов. Не порождает процессы (`delegate_to_subagent`). Только main / supervisor.

## Поиск и ноутбуки

- `tool_search` — поиск builtin, MCP, skills и расширений. `enable_matches=true` включает совпадения только в этой сессии (фильтр слота сохраняется).
- `session_search` — короткие сниппеты из памяти, других сессий и trajectory (не полные транскрипты).
- `notebook_edit` — replace / insert / delete ячейки `.ipynb` внутри jail (`cell_id`, иначе `cell_index`).
- `lsp` — Python через `jedi`, если установлен; иначе `{ok: false, code: lsp_unavailable, fallback: grep}`.
- `plan_mode` — `enter` / `exit` / `status`. В режиме плана наружу отдаются только read-only tools; записи возвращают `plan_mode_blocked`. Выход с непустым планом спрашивает Approve / Revise. План пишется в `.holix/plans/`.

## Слоты (по умолчанию)

| Tools | Слоты |
|-------|--------|
| `apply_patch`, `job_monitor`, `notebook_edit` | `main`, `coder` |
| `ask_user`, `tool_search`, `session_search`, `lsp` | все |
| `subagent_control`, `plan_mode` | `main`, `supervisor` |

## Алиасы

Модели, обученные на Claude Code / Codex / Cline, часто зовут чужие имена. Holix их резолвит:

| Чужое имя | Tool Holix |
|-----------|------------|
| `Read` | `read_file` |
| `Write` | `write_file` |
| `Edit`, `StrReplace` | `patch_file` |
| `Grep` | `grep` |
| `Glob` | `glob` |
| `Bash`, `shell`, `shell_command` | `run_terminal_command` |
| `WebSearch` / `WebFetch` | `web_search` / `fetch_url` |
| `TodoWrite`, `update_plan` | `todo_write` |
| `Skill`, `use_skill` | `skill_view` |
| `Agent`, `Task` | `delegate_to_subagent` |
| `ApplyPatch`, `apply-patch` | `apply_patch` |
| `AskUserQuestion` | `ask_user` |
| `ToolSearch` | `tool_search` |
| `Monitor`, `TaskOutput`, `TaskStop` | `job_monitor` (action: list / tail / kill) |
| `SendMessage` | `subagent_control` (`action=send`) |
| `EnterPlanMode` / `ExitPlanMode` | `plan_mode` (`enter` / `exit`) |
| `LSP` | `lsp` |
| `SessionSearch`, `search_history` | `session_search` |
| `NotebookEdit` | `notebook_edit` |

Короткие имена (`Read`, `Bash`, …) только резолвятся, чтобы MCP мог занять то же имя.

## Code mode

`tools.apply_patch(...)` и остальные новые имена есть в SDK. Записи — последовательно; read-only можно через `tools.parallel`. `ask_user` внутри программы `run_code` по-прежнему запрещён. Внутренние вызовы идут через ActionGuard и jail.
