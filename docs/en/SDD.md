# Spec-Driven Development (SDD) in Holix

> **Idea:** specify first, implement second, archive into main specs last.  
> Layout is compatible with [OpenSpec](https://github.com/javded-itres/OpenSpec).

This page covers: why SDD, the `openspec/` tree, `sdd_*` tools, `/spec` slash commands, skills, **apply modes**, step-by-step **examples** (CLI/TUI and agent-driven), multi-project, understanding gate, and troubleshooting.

Related: [Sub-agents](SUBAGENTS.md) · [Slash Commands](SLASH_COMMANDS.md) · [Hub & Skills](HUB.md) · [Execution Modes](EXECUTION_MODES.md)

---

## Why SDD

| Without SDD | With SDD |
|-------------|----------|
| Agent codes from a chat guess | Fixed **what/why**, then implementation |
| No task graph | `tasks.md` + `assignee` + `depends_on` |
| Specs scattered in chat | Deltas under `openspec/changes/…`, truth in `openspec/specs/` |
| Hard to delegate | `sdd_apply` / `sdd_dispatch` → main or subagents |

Use for non-trivial features, APIs, schemas, product changes — not one-line tweaks.

---

## Workspace layout

```text
openspec/
  config.yaml
  specs/<domain>/spec.md          # source of truth (after archive)
  changes/<change-id>/
    proposal.md
    design.md
    tasks.md
    specs/<domain>/spec.md        # delta ADDED/MODIFIED/REMOVED
    .apply-mode                   # self | subagents | hybrid
  changes/archive/YYYY-MM-DD-<id>/
```

**Rules:**

- There is **no** `openspec/changes/<id>/specs.md` — only `specs/<domain>/spec.md`
- Main domains update **only** via `sdd_archive`
- Fill change artifacts with **`sdd_write_artifact`**, not raw `write_file`

### Multi-project

```text
repo/
  openspec/              # project=""
  apps/api/openspec/     # project="apps/api"
```

1. `sdd_list_projects`
2. Pass `project=<path>` on every `sdd_*` call

---

## Agent tools (`sdd_*`)

| Tool | Purpose |
|------|---------|
| `sdd_list_projects` | Projects that already have `openspec/` |
| `sdd_init` | Scaffold layout |
| `sdd_list_specs` / `sdd_read_spec` | Main specs |
| `sdd_list_changes` | Active / archived changes |
| `sdd_create_change` | Scaffold change (**stubs only**) |
| `sdd_write_artifact` | proposal \| design \| tasks \| specs |
| `sdd_status` | Overview or one change + paths |
| `sdd_update_understanding` / `sdd_confirm_understanding` | Understanding gate |
| `sdd_set_task_assignee` | `main` or subagent type |
| `sdd_check_task` | Mark task done |
| `sdd_request_apply_mode` / `sdd_set_apply_mode` | self \| subagents \| hybrid |
| `sdd_apply` | Start apply |
| `sdd_dispatch` | Spawn subagents for ready tasks |
| `sdd_archive` | Merge delta → main + archive |

---

## Slash `/spec`

```text
/spec
/spec init
/spec propose <change-id>
/spec status [change-id]
/spec mode <change-id> self|subagents|hybrid
/spec apply <change-id>
/spec archive <change-id>
```

Skills:

| Skill | Phase |
|-------|--------|
| `/holix-sdd-propose` | Spec + tasks, **no product code** |
| `/holix-sdd-apply` | Implement tasks |
| `/holix-sdd-archive` | Merge + archive |

---

## Apply modes

Chosen by the **user** after a ready change:

| Mode | Who codes | Assignees |
|------|-----------|-----------|
| **self** | Main agent only | Ignored |
| **subagents** | Subagents only | Required; graph-driven |
| **hybrid** | Main + subagents | `main` stays on main |

Waves: ready tasks (deps done) spawn first; after `sdd_check_task`, next wave.

---

## `tasks.md` format (required)

OpenSpec Holix checklist only. Free-form `## 1. …` + Description/Assignee sections are **rejected**.

```markdown
# Tasks: add-oauth

## 1. Backend

- [ ] 1.1 OAuth endpoints
  - **assignee:** `coder`
  - **reason:** isolated API
  - **depends_on:**

- [ ] 1.2 Shared auth config
  - **assignee:** `main`
  - **reason:** conflict-prone
  - **depends_on:** `1.1`

## 2. Frontend

- [ ] 2.1 Login UI
  - **assignee:** `coder`
  - **depends_on:** `1.1`
```

### Spec delta sample

```markdown
# Spec delta: auth

## ADDED Requirements

### Requirement: OAuth login
The system SHALL allow users to sign in with OAuth 2.0.

#### Scenario: Successful Google login
- **GIVEN** a valid Google account
- **WHEN** the user completes the OAuth redirect
- **THEN** a session is created
```

---

## Example 1 — full cycle (CLI/TUI)

**User:** “Add `GET /api/health` and tests.”

### A — propose (no product code)

```text
sdd_list_projects
sdd_status / sdd_init if needed
sdd_list_specs + sdd_read_spec
sdd_create_change(change_id="api-health", request="…", domain="api")
# understanding gate if enabled → confirm
sdd_write_artifact(… proposal, specs, design, tasks …)
sdd_status(change_id="api-health")  # apply_ready
# stop for user review
```

### B — mode + apply

```text
sdd_set_apply_mode(change_id="api-health", mode="self")
sdd_apply(change_id="api-health")
# implement tasks
sdd_check_task(change_id="api-health", task_id="1.1", done=true)
```

### C — archive

```text
sdd_archive(change_id="api-health")
```

---

## Example 2 — multi-project + subagents

```text
sdd_list_projects
# path: apps/api
sdd_create_change(project="apps/api", change_id="rate-limit", request="…")
# all further calls with project="apps/api"
sdd_set_apply_mode(…, mode="subagents")
sdd_apply(…)
sdd_dispatch(…)
sdd_archive(…)
```

Tasks with `depends_on` form the execution graph; same type on multiple ready tasks → parallel `coder-1`, `coder-2`.

---

## Example 3 — hybrid

```markdown
- [ ] 1.1 Shared types
  - **assignee:** `main`
- [ ] 2.1 API
  - **assignee:** `coder`
  - **depends_on:** `1.1`
- [ ] 2.2 CLI
  - **assignee:** `coder`
  - **depends_on:** `1.1`
```

Main does 1.1; 2.1 and 2.2 run in parallel afterward.

---

## Understanding gate

Before full propose (when enabled):

1. Read main + archived specs  
2. Project context / `HOLIX.md` (run `/init` if weak)  
3. `sdd_update_understanding` with honest score  
4. Residual questions only  
5. `sdd_confirm_understanding` when score ≥ threshold  
6. Then `sdd_write_artifact`

---

## Happy-path checklist

```text
[ ] sdd_list_projects / project=
[ ] sdd_init if needed
[ ] read main specs
[ ] sdd_create_change + request=
[ ] understanding confirm if on
[ ] sdd_write_artifact ×4
[ ] sdd_status → apply_ready
[ ] USER picks mode
[ ] sdd_apply → dispatch → check tasks
[ ] sdd_archive
```

---

## Do NOT

| Mistake | Do this |
|---------|---------|
| Code during propose | Spec + tasks first |
| `write_file` into openspec change | `sdd_write_artifact` |
| `specs.md` at change root | `artifact=specs` + `domain=` |
| Free-form tasks | Checklist + `**assignee:**` |
| Archive early | All tasks done + review |
| Mixed languages | One locale: ru **or** en |

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `apply_ready: false` | Artifacts / mode / assignees incomplete |
| tasks rejected | OpenSpec checklist only |
| understanding block | update score + confirm |
| path not found | `sdd_status` → `artifact_paths` |
| no subagents | mode + ready deps + `sdd_dispatch` |

---

## Quick agent reference

```text
sdd_init(project="", example_domain="app")
sdd_create_change(change_id="feature-x", request="…")
sdd_write_artifact(change_id="feature-x", artifact="proposal", content="…")
sdd_write_artifact(change_id="feature-x", artifact="specs", domain="app", content="…")
sdd_write_artifact(change_id="feature-x", artifact="tasks", content="…")
sdd_set_apply_mode(change_id="feature-x", mode="self")
sdd_apply(change_id="feature-x")
sdd_check_task(change_id="feature-x", task_id="1.1", done=true)
sdd_archive(change_id="feature-x")
```

Tell the user: “Start with `/spec propose …` or skill `holix-sdd-propose`.”
