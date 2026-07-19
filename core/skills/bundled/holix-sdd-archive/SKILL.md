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
4. Report merged main specs paths and archive folder under `openspec/changes/archive/`

## Effects

- Delta `## ADDED|MODIFIED|REMOVED Requirements` merged into `openspec/specs/<domain>/spec.md`
- Change directory moved to `openspec/changes/archive/YYYY-MM-DD-<change-id>/`

## Do NOT

- Do not archive without user intent for incomplete work
- Do not delete main specs; archive only moves the change folder after merge
