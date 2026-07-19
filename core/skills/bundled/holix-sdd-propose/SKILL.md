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

## Multi-project workspaces

A workspace may contain several projects, each with its own `openspec/`.

1. `sdd_list_projects` — pick the project `path` (empty string = workspace root)
2. Pass `project=<path>` to **every** subsequent `sdd_*` tool for that work

## Workflow (propose)

1. `sdd_status` with `project=` — if not initialized → `sdd_init` with the same `project=`
2. `sdd_list_specs` + `sdd_read_spec` for relevant domains
3. `sdd_list_changes` — avoid duplicate open changes
4. `sdd_create_change` with slug id **and** `request=` (user request text)
5. **Understanding gate** (if enabled in user prefs — see create_change response):
   - Call `sdd_update_understanding` with your honest `score` (0–100), `summary`, and `questions`
   - Present questions to the user; after each answer call again with `user_answer` and updated `score`
   - If `score < threshold` → keep clarifying (status `clarifying`)
   - If `score ≥ threshold` → status `ready`: offer **proceed** or **more questions**
   - If later answers drop `score` below threshold → new clarifying cycle
   - Only after user agrees to proceed: `sdd_confirm_understanding`
   - **Do not** fill full proposal/specs/tasks until confirmed (or gate disabled/`skipped`)
6. Fill artifacts via `sdd_write_artifact`:
   - **proposal** — Why / What / Impact
   - **specs** — delta with `## ADDED|MODIFIED|REMOVED Requirements` and GIVEN/WHEN/THEN
   - **design** — approach + task→assignee table
   - **tasks** — checklist with assignees (see below)

### Assignees (you choose who does the work)

1. Call `list_subagent_types` first.
2. **Custom types** (user-created Agents tab): prefer matching custom agents by role.
3. **No custom types**: pick a built-in (`coder`, `reviewer`, `researcher`, `analyst`, `writer`, `web_researcher`) that fits each task.
4. **`main`**: shared / risky / merge-conflict work that must stay on the main agent.
5. Apply mode is chosen later by the user:
   - **self** — assignees are ignored; main does everything (no need to over-optimize assignees).
   - **subagents / hybrid** — assignees drive dispatch; same type on many tasks → parallel jobs `type-1`, `type-2`, …

### tasks.md format (required)

```markdown
- [ ] 1.1 Add OAuth endpoints
  - **assignee:** `coder`
  - **reason:** isolated API surface

- [ ] 1.2 Shared auth config
  - **assignee:** `main`
  - **reason:** conflict-prone shared code
```

Assignees: `main` or a type name from `list_subagent_types` (custom or built-in).

7. `sdd_status` with `change_id` until `apply_ready: true`
8. Stop and let the user review. **Do not implement** until apply skill / user asks.

## Do NOT

- Do not write product code during propose
- Prefer real type names for subagents/hybrid; `unassigned` is OK for mode `self` (runs on main), but blocks apply-ready for pure `subagents`
- Do not skip reading main specs for brownfield work
- Do not skip understanding gate when it is enabled and status is not `confirmed`/`skipped`
