# Coding-agent tools

Holix keeps a small tool set. New names below match the useful parts of Claude Code, Codex, and DeepSeek Harness — they go through the same `BaseTool` registry, ActionGuard, and workspace jail as `patch_file` / `grep`.

## File edits: `patch_file` vs `apply_patch`

| Family | Prefer |
|--------|--------|
| Claude, Qwen, DeepSeek | `patch_file` — exact unique `old_string` → `new_string` (or `replacements=[…]`) |
| GPT / Codex | `apply_patch` — Codex document (`*** Begin Patch` … `*** End Patch`) |

Use `write_file` only to create a file or replace it entirely. Prefer `grep` / `glob` over `rg` / `find` in the shell. If a shell command looks like `apply_patch <<'EOF' …`, Holix routes it to the `apply_patch` tool and asks the model to call that tool directly next time.

`apply_patch` is atomic: any hunk that does not unique-match fails the whole call (`code: hunk_mismatch`) and writes nothing. `dry_run=true` returns the intended diff without touching disk.

## Questions: `ask_user`

Available on **every** agent slot (main and sub-agents). Pass `questions` (1–5). Each item can have up to 8 option buttons, `multi_select`, and `allow_free_text`.

Legacy `question` + `context` still works (wrapped as `questions[0]`). The agent loop blocks until the human answers or the confirmation timeout fires (`code: timeout`).

TUI: modal with option buttons and a text field. Telegram / MAX: inline buttons (`callback_data` is a short token). Free text = reply to the question message.

## Jobs and sub-agents

- `job_monitor` — `list` / `tail` / `wait` / `kill` on `start_background_process` jobs. `job_id` required except for `list`.
- `subagent_control` — `list` / `status` / `send` / `interrupt` / `collect` on **already running** sub-agents. Does not spawn (use `delegate_to_subagent`). Main / supervisor only.

## Discovery and notebooks

- `tool_search` — search builtin, MCP, skill, and extension names+descriptions. `enable_matches=true` activates top hits for **this session only** (still filtered by the slot allowlist).
- `session_search` — short snippets from memory, other sessions, and trajectory traces (not full transcripts).
- `notebook_edit` — replace / insert / delete a cell in a `.ipynb` inside the jail (`cell_id` first, else `cell_index`).
- `lsp` — hover / definition / references / symbols / diagnostics. Uses an installed language server for the file type (Python jedi or pylsp, JS/TS, Go, Rust, JSON/HTML/CSS, YAML, Bash, …). Missing server → `{ok: false, code: lsp_unavailable, install: […], fallback: grep}`. Setup: `holix lsp setup`, `holix doctor`.
- `plan_mode` — `enter` / `exit` / `status`. While on, only read-only tools are offered; writes return `plan_mode_blocked`. Exit with a non-empty plan asks Approve / Revise. Plans save under `.holix/plans/` when that store is already used.

### Language servers (`lsp`)

The `lsp` tool talks to **installed** servers on PATH (plus in-process Python `jedi`). It does not download compilers itself. `holix lsp setup` installs the servers you pick **and** missing toolchains they need (Node.js, Go, rustup, Ruby, Homebrew formulae).

| Language | Server | Install |
|----------|--------|---------|
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
holix lsp status                 # what is ready
holix lsp setup                  # interactive picker (recommended / all / missing / optional / 12,go)
holix lsp setup --yes            # recommended, no prompt
holix lsp setup --all            # every catalog server + toolchains
holix lsp setup --missing        # everything not ready
holix lsp setup --optional       # Go, Rust, C/C++, Vue, …
holix lsp setup --ids go,rust,vue
# mixed selection (prompt or --ids):
#   recommended,go,rust
#   python js go
holix doctor                     # reports missing servers
holix doctor --fix               # installs Pyright when missing
holix bootstrap                  # offers recommended install on first-run setup
```

`action=status` lists ready servers without a file path.

## Slot allowlists (defaults)

| Tools | Slots |
|-------|--------|
| `apply_patch`, `job_monitor`, `notebook_edit` | `main`, `coder` |
| `ask_user`, `tool_search`, `session_search`, `lsp` | all |
| `subagent_control`, `plan_mode` | `main`, `supervisor` |

## Aliases (foreign names)

Models trained on Claude Code / Codex / Cline often emit other names. Holix maps them:

| Foreign name | Holix tool |
|--------------|------------|
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
| `Monitor`, `TaskOutput`, `TaskStop` | `job_monitor` (action inferred: list / tail / kill) |
| `SendMessage` | `subagent_control` (`action=send`) |
| `EnterPlanMode` / `ExitPlanMode` | `plan_mode` (`enter` / `exit`) |
| `LSP` | `lsp` |
| `SessionSearch`, `search_history` | `session_search` |
| `NotebookEdit` | `notebook_edit` |

Aliases are resolve-only for short names (`Read`, `Bash`, …) so an MCP tool can still own that name.

## Code mode

`tools.apply_patch(...)`, `tools.job_monitor(...)`, and the other new names are on the generated SDK. Writes stay serial; `risk_level: no` tools may use `tools.parallel`. `ask_user` remains forbidden inside a `run_code` program (interactive). Inner calls still go through ActionGuard and the jail.
