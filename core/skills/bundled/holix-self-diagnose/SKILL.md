---
name: holix-self-diagnose
description: >
  When the user says Holix is wrong or asks it to check itself
  («проверь себя», «почему ты делаешь не так», «ты отвечаешь неправильно»,
  check yourself), call self_diagnose, then answer from the report.
tags:
  - self-diagnose
  - session
  - honesty
  - holix
  - required
required: true
user-invocable: true
---

## When to use

The user is criticizing **this agent**, not asking to debug their own code:

- «проверь себя», «проверь свою работу», «самодиагностика»
- «почему ты делаешь не так», «ты отвечаешь неправильно»
- «check yourself», «you're answering incorrectly»

## Procedure

1. Call `self_diagnose` immediately (pass their complaint as `complaint` if useful).
2. Read `findings`, `plan`, `session.timeline`, `session.last_real_ask`, failed tools.
3. Tell the user what went wrong in **this session** (tools vs claims vs errors). Skills only if a finding is `skill_*`.
4. Immediately execute `plan.do_now` with tools (send file, retry, finish the last ask).
5. Ask the user only about `plan.ask_user` (e.g. continue after step limit).
6. If `skill_fixes` staged a patch, quote the `proposal_id`.

## Pitfalls

- Do not answer the complaint from memory. The session transcript is in the tool result.
- Do not dump or patch unrelated skills. File-delivery skill fix only when the session is about sending files.
- `read_file` / `cat` is not delivering a file. `self_diagnose` will flag that.
- Do not auto-spawn sub-agents for this. Main agent only.

## Verification

- This turn has a `self_diagnose` tool result.
- The reply quotes findings (`code` + `next_action`), not a generic apology.
