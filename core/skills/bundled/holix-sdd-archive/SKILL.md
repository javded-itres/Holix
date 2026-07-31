---
name: holix-sdd-archive
description: Archive a completed SDD change — merge delta specs into main openspec/specs and move change to archive
tags:
  - sdd
  - openspec
  - archive
  - holix
user-invocable: true
---

## When to use

Change is implemented (tasks checked) and user wants to close it / merge requirements into the source of truth.

## Workflow

1. `sdd_status` with `change_id` — review remaining open tasks
2. Confirm with user if any tasks incomplete
3. `sdd_archive` with `change_id`
4. Report `merged_specs`, any `warnings` (open tasks / not apply_ready), and archive path under `openspec/changes/archive/`

## Effects

- Delta `## ADDED|MODIFIED|REMOVED Requirements` merged into `openspec/specs/<domain>/spec.md`
- Nested `specs/<domain>/**/spec.md` still merges into **that domain** (not a nested folder name as a new domain)
- Sections apply in **document order** (later REMOVED of the same title wins over earlier MODIFIED)
- Duplicate requirement titles in main collapse to one block
- Change directory moved to `openspec/changes/archive/YYYY-MM-DD-<change-id>/`
- Open tasks do **not** block archive; tool returns `warnings` — surface them to the user

## Merge gotchas

| Issue | Behavior |
| --- | --- |
| Same title ADDED when already in main | Body replaced (treated as modify) |
| REMOVED then MODIFIED same title | **Last section in the delta file wins** |
| Nested `specs/auth/notes/spec.md` | Merges into **auth**, not domain `notes` |
| Incomplete tasks | Archive still runs; check `warnings` |

## Do NOT

- Do not archive without user intent for incomplete work
- Do not delete main specs; archive only moves the change folder after merge
- Do not invent main specs by hand after archive — trust `merged_specs` paths
