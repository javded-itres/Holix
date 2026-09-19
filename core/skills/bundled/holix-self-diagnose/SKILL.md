---
name: holix-self-diagnose
description: >
  When the user says Holix is wrong or asks it to check itself
  («проверь себя», «почему ты делаешь не так», «ты отвечаешь неправильно»,
  check yourself), spawn the session_doctor sub-agent with a clean context.
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

### Main agent

1. Spawn a **clean-context** doctor (do not fork parent turns):
   `delegate_to_subagent(agent_type="session_doctor", fork=false, task=…)`.
2. In `task` include this `conversation_id` and the user's complaint.
3. `wait_subagent_result` and show the doctor's briefing.
4. Do **not** call `self_diagnose` yourself (this chat is polluted).
5. Do **not** change system settings, skills, or extensions.

### session_doctor (you already are the child)

1. Call `self_diagnose` immediately (parent session is autopsied automatically).
2. Read `findings`, `plan`, `session.timeline`, `session.last_real_ask`, `llm`, `settings`.
3. Explain what went wrong in **this session** (tools vs claims vs user prompts vs settings).
4. Coach the user: how to write the next prompt and how to use Holix so the mistake does not repeat.
5. Do **not** write files, patch skills, run the terminal, or change system settings.
6. If an operator must change model / jail / extensions or read logs: call `request_admin_support`.
   That tool **always asks the user to confirm**. Deny = send nothing. Do not retry after Deny.

## Pitfalls

- Do not answer the complaint from memory. The autopsy is in `self_diagnose`.
- `read_file` / `cat` is not delivering a file. The report will flag that.
- Do not auto-spawn any type other than `session_doctor` for this request.
- Never claim a support ticket was sent unless `request_admin_support` returned `ok: true`.

## Verification

- Main: this turn spawned `session_doctor` (`fork=false`) and waited.
- Doctor: this turn has a `self_diagnose` result and quotes finding codes.
