---
name: web-researcher
description: >
  Optional guide for web_researcher sub-agent. Use only when the user explicitly
  asks to delegate web research (e.g. /subagent-spawn web_researcher, "запусти
  web_researcher").
tags:
  - research
  - web
  - search
  - subagent
  - delegate
user-invocable: true
---

## When to use

Only when the user **explicitly** requests the `web_researcher` sub-agent
(`/subagent-spawn web_researcher …`, "делегируй web_researcher", etc.).
Do not auto-spawn for ordinary search questions.

## How to delegate

1. `delegate_to_subagent(agent_type="web_researcher", task="<full user request>")`
2. `wait_subagent_result(job_id="<returned job_id>")` if the user wants the answer in this reply
3. Summarize the sub-agent response for the user

## Task text

Include in `task`: what to find, geography/route, date (today), preferred sources, output format.