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

- `tool_search` — поиск builtin, MCP, skills и расширений. В LLM **tools** только **ядро** (файлы, shell, `lsp`, `ask_user`, `skill_view`, …). Остальное (MCP, browser, SDD, SQL, notebook, jobs, session search, …) отложенное. `enable_matches=true` (по умолчанию) подключает совпадения **на эту сессию** (фильтр слота сохраняется). `HOLIX_LAZY_TOOLS=0` — полный каталог.
- `session_search` — короткие сниппеты из памяти, других сессий и trajectory (не полные транскрипты).
- `notebook_edit` — replace / insert / delete ячейки `.ipynb` внутри jail (`cell_id`, иначе `cell_index`).
- `lsp` — **навигация**: hover / definition / references / symbols / implementation; `diagnostics` — один известный файл (не lint всего репозитория). Language server для типа файла (Python jedi или pylsp, JS/TS, Go, Rust, JSON/HTML/CSS, YAML, Bash, …). Нет сервера → `{ok: false, code: lsp_unavailable, install: […], fallback: grep}`. Настройка: `holix lsp setup`, `holix doctor`.
- `plan_mode` — `enter` / `exit` / `status`. В режиме плана наружу отдаются только read-only tools; записи возвращают `plan_mode_blocked`. Выход с непустым планом спрашивает Approve / Revise. План пишется в `.holix/plans/`.

### Language servers (`lsp`)

Инструмент `lsp` ходит в **установленные** серверы в PATH (и встроенный Python `jedi`). Сам компиляторы не качает. `holix lsp setup` ставит выбранные серверы **и** недостающие тулчейны (Node.js, Go, rustup, Ruby, формулы Homebrew).

| Язык | Сервер | Установка |
|------|--------|-----------|
| Python | **Pyright** (`pyright-langserver`) | `pip install "Holix[lsp]"` / `pip install pyright` |
| JS / TS | `typescript-language-server` | `npm install -g typescript typescript-language-server` |
| JSON / HTML / CSS | vscode langservers | `npm install -g vscode-langservers-extracted` |
| YAML | `yaml-language-server` | `npm install -g yaml-language-server` |
| Bash | `bash-language-server` | `npm install -g bash-language-server` |
| Dockerfile | `docker-langserver` | `npm install -g dockerfile-language-server-nodejs` |
| Go | `gopls` | `go install golang.org/x/tools/gopls@latest` |
| Rust | `rust-analyzer` | `rustup component add rust-analyzer` |
| C / C++ | `clangd` | `brew install llvm` / `apt install clangd` |

```bash
holix lsp status                 # что готово
holix lsp setup                  # выбор: recommended / all / missing / optional / 12,go
holix lsp setup --yes            # рекомендованные, без вопросов
holix lsp setup --all            # весь каталог + тулчейны
holix lsp setup --missing        # всё, что ещё не ready
holix lsp setup --optional       # Go, Rust, C/C++, Vue, …
holix lsp setup --ids go,rust,vue
# смешанный выбор (промпт или --ids):
#   recommended,go,rust
#   python js go
holix doctor
holix doctor --fix               # поставит Pyright, если его нет
holix bootstrap                  # при первой настройке — recommended
```

`action=status` — список готовых серверов без пути к файлу.

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
