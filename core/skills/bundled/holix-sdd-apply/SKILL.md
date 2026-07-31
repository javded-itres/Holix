---
name: holix-sdd-apply
description: Implement an SDD change from tasks.md — always ask self vs subagents first, then execute only after apply mode is set
tags:
  - sdd
  - openspec
  - apply
  - implement
  - subagents
  - holix
user-invocable: true
---

## When to use

User says implement / apply / do the change after a proposal exists under `openspec/changes/<id>/`.

## Mandatory pre-apply gate

**Before any product code:**

1. `sdd_status` with `change_id` — must be `apply_ready`
2. `sdd_request_apply_mode` — get the question
3. **Ask the user in chat** (show the prompt):

   - **self** — main agent does all tasks  
   - **subagents** — dispatch by assignee (`main` stays on main)  
   - **hybrid** — strictly follow each assignee  

4. Wait for the answer. Then `sdd_set_apply_mode` with `self` | `subagents` | `hybrid`
5. `sdd_apply` — only proceeds if mode is set; returns plan (task → executor).  
   For **subagents/hybrid** it **auto-dispatches** using the **exact assignee** from `tasks.md` (e.g. `coder-python`).

If mode is missing, `sdd_apply` fails on purpose. **Do not start coding.**

## Implement

1. Follow the plan from `sdd_apply` only; respect delta specs
2. Mode **self**: you execute every task (ignore assignees; do not spawn subagents)
3. Mode **subagents** / **hybrid**: trust auto-dispatch / `sdd_dispatch` job ids — they use **tasks.md assignee** (custom types). Same type → `type-1`, `type-2`, … in parallel. Dispatch budgets `max_steps` from each task's **size** (`xs`/`s`/`m`). Then `wait_subagent_result`; do `main` tasks yourself.  
   **Successful subagent jobs auto-mark their task checkbox** in `tasks.md` — you do not need `sdd_check_task` for those. Still call `sdd_check_task` for **main** tasks and if auto-mark failed.
4. After each **main** task: `sdd_check_task`
5. When all done: suggest archive (`holix-sdd-archive` / `sdd_archive`)
6. If a sub-agent thrash-fails on a still-large task: **split** that task in `tasks.md` into smaller XS/S items and re-dispatch — do not just raise max_steps

## Do NOT

- Do not code before user chooses apply mode
- Do not invent tasks outside `tasks.md`
- Do **not** call `delegate_to_subagent` with built-in `coder` when assignee is a custom type (`coder-python`, …) — that ignores the user's agent
- Do not archive until user agrees (unless they asked)
