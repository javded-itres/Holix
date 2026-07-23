---
name: holix-sdd-propose
description: Create Spec-Driven Development changes (OpenSpec-style) — multi-project openspec, understanding gate, assigned tasks before coding
tags:
  - sdd
  - openspec
  - propose
  - specs
  - holix
user-invocable: true
---

## When to use

User wants a **non-trivial feature, API, schema, or product change**. Work starts with a **specification**, not code.

## Language (Studio locale)

Match the user's Studio UI language (**`ru`** or **`en`** only):

- Chat (questions, summaries, progress) — that language only
- All SDD artifacts via `sdd_write_artifact` (proposal, design, specs, tasks) — that language only
- `sdd_update_understanding` `summary` / `questions` — that language only
- **Do not mix** languages; do not write specs in the other language
- Structural OpenSpec markers may stay English (`## ADDED Requirements`, `GIVEN`/`WHEN`/`THEN`), but narrative text, requirement titles, scenarios, and task descriptions must be in the selected locale

If the Studio prompt states `locale=ru` or `locale=en`, treat that as authoritative.

## Multi-project workspaces

A workspace may contain several projects, each with its own `openspec/`.

1. `sdd_list_projects` — pick the project `path` (empty string = workspace root)
2. Pass `project=<path>` to **every** subsequent `sdd_*` tool for that work

## Workflow (propose)

1. `sdd_status` with `project=` — if not initialized → `sdd_init` with the same `project=`
2. `sdd_list_specs` + `sdd_read_spec` for relevant domains
3. `sdd_list_changes` — avoid duplicate open changes
4. `sdd_create_change` with slug id **and** `request=` (user request text)
5. **Understanding gate** (if enabled in user prefs — see create_change response).

   **Before any clarifying questions to the user**, complete this order:

   1. **Existing SDD knowledge**
      - `sdd_list_specs` + `sdd_read_spec` for relevant domains (`openspec/specs/`)
      - `sdd_list_changes` with `include_archive=true`
      - Read related **archived** change artifacts under `openspec/changes/archive/`
        (proposal, specs, design, tasks) and any overlapping open changes
   2. **Project context / `/init` if needed**
      - Read `.holix/HOLIX.md` (and project-local notes if any)
      - If missing, empty, or insufficient for this request/domain: run project
        onboarding equivalent to **`/init`** for the project path (scan layout +
        key files; update HOLIX.md via `update_holix_section`, or ask the user once
        to run `/init <path>` if you cannot write). Do not skip when the codebase
        is unknown.
   3. **Assess understanding**
      - Call `sdd_update_understanding` with honest `score` (0–100) and `summary`
        of what you learned from main specs, archives, and HOLIX — **before**
        dumping questions at the user
   4. **Only then** ask residual clarifying questions in chat
      - After each answer: `sdd_update_understanding` again with `user_answer` and
        updated `score` / `questions`
      - If `score < threshold` → keep clarifying (status `clarifying`)
      - If `score ≥ threshold` → status `ready`: offer **proceed** or **more questions**
      - If later answers drop `score` below threshold → new clarifying cycle
   5. Only after user agrees to proceed: `sdd_confirm_understanding`
   - **Do not** fill full proposal/specs/tasks until confirmed (or gate disabled/`skipped`)
   - **Do not** open with a long questionnaire before steps 1–3
6. Fill artifacts via `sdd_write_artifact` only (not `write_file` / inventing paths):
   - **proposal** → `openspec/changes/<id>/proposal.md`
   - **design** → `openspec/changes/<id>/design.md`
   - **tasks** → `openspec/changes/<id>/tasks.md`
   - **specs** → `openspec/changes/<id>/specs/<domain>/spec.md` (pass `domain=` or omit)
   - There is **no** `openspec/changes/<id>/specs.md` — do not `read_file` that path
   - Prefer `sdd_status(change_id=…)` → `artifact_paths` before reading anything
   - **proposal** content — Why / What / Impact
   - **specs** content — delta with `## ADDED|MODIFIED|REMOVED Requirements` and GIVEN/WHEN/THEN
   - **design** content — approach + task→assignee table
   - **tasks** content — checklist with assignees (see below)

### Assignees (you choose who does the work)

1. Call `list_subagent_types` first.
2. **Custom types** (user-created Agents tab): prefer matching custom agents by role.
3. **No custom types**: pick a built-in (`coder`, `reviewer`, `researcher`, `analyst`, `writer`, `web_researcher`) that fits each task.
4. **`main`**: shared / risky / merge-conflict work that must stay on the main agent.
5. Apply mode is chosen later by the user:
   - **self** — assignees are ignored; main does everything (no need to over-optimize assignees).
   - **subagents / hybrid** — assignees drive dispatch; **task graph** controls order:
     only **ready** tasks spawn (deps done); later waves auto-dispatch after completion.
     Same type on many **ready** tasks → parallel jobs `type-1`, `type-2`, …

### tasks.md format (required — OpenSpec Holix checklist only)

Studio and `sdd_*` tools parse **only** checkbox lines. Free-form sections are **rejected**.

**Correct (required):**

```markdown
# Tasks: <change-id>

## 1. Implementation

- [ ] 1.1 Add OAuth endpoints
  - **assignee:** `coder`
  - **reason:** isolated API surface
  - **depends_on:**

- [ ] 1.2 Wire UI to OAuth (after API)
  - **assignee:** `coder`
  - **reason:** needs 1.1
  - **depends_on:** `1.1`

- [ ] 1.3 Shared auth config
  - **assignee:** `main`
  - **reason:** conflict-prone shared code
  - **depends_on:** `1.1`
```

**Wrong (not visible in UI — do not use):**

```markdown
## 1. Add OAuth endpoints
- **Описание:** …
- **Исполнитель:** coder
- **Результат:** …
```

Rules:
- Every task is `- [ ] <id> <title>` (or `- [x]` when done)
- Nested `  - **assignee:** \`type\`` is mandatory structure (`main`, subagent type, or `unassigned`)
- Optional `  - **reason:** …`
- Optional `  - **depends_on:** \`1.1, 1.2\`` — execution graph (empty = no explicit deps)
- Same-section order (1.1 before 1.2) is **inferred** when `depends_on` is empty
- Parallel work: independent sections (1.x vs 2.x) or shared `depends_on` only
- Use `sdd_write_artifact(artifact=tasks, …)` only — never invent another schema

Assignees: `main` or a type name from `list_subagent_types` (custom or built-in).

7. `sdd_status` with `change_id` until `apply_ready: true`
8. Stop and let the user review. **Do not implement** until apply skill / user asks.

## Do NOT

- Do not write product code during propose
- Prefer real type names for subagents/hybrid; `unassigned` is OK for mode `self` (runs on main), but blocks apply-ready for pure `subagents`
- Do not skip reading main specs for brownfield work
- Do not skip understanding gate when it is enabled and status is not `confirmed`/`skipped`
- Do not write SDD artifacts or clarifying questions in a language other than the user's Studio locale (`ru` or `en`)
