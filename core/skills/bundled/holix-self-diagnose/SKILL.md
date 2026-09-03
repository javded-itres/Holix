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
2. Read `findings`, `session.tools`, `llm`, and `skill_fixes`.
3. Tell the user what actually happened (tools vs claims). Do not invent a send/write.
4. If a finding says to call another tool (`send_chat_files`, `research_site_pages`, …), call it next.
5. If `skill_fixes` staged a patch, quote the `proposal_id` and whether it is live or waiting for approval.

## Pitfalls

- Do not answer the complaint from memory. The session transcript is in the tool result.
- `read_file` / `cat` is not delivering a file. `self_diagnose` will flag that.
- Do not auto-spawn sub-agents for this. Main agent only.

## Verification

- This turn has a `self_diagnose` tool result.
- The reply quotes findings (`code` + `next_action`), not a generic apology.
