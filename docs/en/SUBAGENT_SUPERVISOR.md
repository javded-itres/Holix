# Subagent Supervisor (runtime orchestrator)

**Status:** Phase 1 (runtime sidecar) + Phase 1.5 (graph-native rework cycle)  
**Date:** 2026-07-30  
**Related:** `core/runtime/step_budget.py`, `core/subagents/manager.py`, plan-wave `orchestrator.py`  
**Code:**  
- Runtime: `core/subagents/supervisor.py`, `SubAgentSupervisorEvent`  
- Graph: `core/graph/nodes/supervisor_node.py`, plan_execute edges  
  `collect → supervisor → (rework? delegate : react)`  
- Tests: `tests/test_subagent_supervisor.py`, `tests/test_graph_supervisor.py`  

**User docs:** [SUBAGENTS.md](SUBAGENTS.md) · [EXECUTION_MODES.md](EXECUTION_MODES.md) · [CONFIGURATION.md](CONFIGURATION.md)

## Problem

When a sub-agent loops, thrash-fails, or hangs, Holix today either:

- extends wait/step budget if there is still progress, or  
- stops / times out the job.

The **main agent does not intervene mid-run** with diagnosis and course correction. The same job is not guided toward recovery.

## Goal

A background **Subagent Supervisor** (worker attached to the main agent run):

1. Watches running sub-agent status, activity, and recent tools.  
2. Detects loop / thrash / hang / stall.  
3. Diagnoses a short root-cause summary.  
4. Sends **guidance** (or revise hint) to the **same** sub-agent.  
5. Caps interventions to avoid recursion / cost blow-ups.  
6. Emits UI events so Studio/CLI can show interventions.

This is **not** the plan-wave builder (`orchestrator.py`). Naming: **Supervisor**.

## Architecture

```
main agent
  └─ SubAgentManager.spawn(...)
        └─ SubagentSupervisor.ensure_running()
              └─ asyncio watch_loop (poll 3–5s)
                    ├─ assess(handle) → Diagnosis
                    ├─ build_guidance(diagnosis)
                    ├─ bus.send(guidance) → same job
                    └─ SubAgentSupervisorEvent
  └─ async_runner / process loop
        └─ each step: drain inbox → inject system message
```

### MVP scope (Phase 1)

| Item | In MVP |
|------|--------|
| Asyncio supervisor task | ✅ |
| Detect: LOOP, THRASH, HUNG, STALL | ✅ |
| Heuristic diagnosis text (no extra LLM) | ✅ |
| Inject `guidance` into async sub-agents | ✅ |
| Config flags + limits | ✅ |
| Events + unit tests | ✅ |
| Process-mode guidance via input_queue | ✅ if low-cost |
| LLM diagnosis | ❌ Phase 2 |
| `revise` rewrite of full task | ❌ Phase 2 |
| OS subprocess supervisor | ❌ Phase 2/3 |
| Studio panel | ❌ Phase 3 |

### Config (env / Settings)

| Key | Default | Meaning |
|-----|---------|---------|
| `HOLIX_SUBAGENT_SUPERVISOR_ENABLED` | `true` | Master switch |
| `HOLIX_SUBAGENT_SUPERVISOR_POLL_S` | `4.0` | Watch interval |
| `HOLIX_SUBAGENT_SUPERVISOR_IDLE_S` | `90.0` | Hang threshold |
| `HOLIX_SUBAGENT_SUPERVISOR_MAX_INTERVENTIONS` | `3` | Per job |
| `HOLIX_SUBAGENT_SUPERVISOR_COOLDOWN_S` | `45.0` | Min gap between interventions |

### Detection (reuse step-budget traces)

- **LOOP** — same tool+args signature 3× in a row (activity log / tool history).  
- **THRASH** — last ≥3 tool results all look like errors.  
- **HUNG** — `RUNNING` and not `is_actively_working(idle_s)`.  
- **STALL** — enough steps taken, no progress markers, not OK.  
- **OK** — recent progress or idle window not exceeded → no action.

### Intervention

`AgentMessage(msg_type="guidance", content=..., metadata={kind, attempt, ...})`

Sub-agent loop, before the next LLM call:

```
while msg := receive(timeout=0):
  if msg_type == "guidance":
    messages.append(system: SUPERVISOR GUIDANCE ...)
```

After max interventions without recovery: log + emit event; do **not** auto-kill in MVP (main/wait/timeout still own termination). Phase 2 may escalate/terminate.

### Events

`SubAgentSupervisorEvent`: name, kind, attempt, message, severity.

### Non-goals (MVP)

- Supervisor must not raise sub-agent permissions.  
- No infinite guidance loops (cooldown + max interventions).  
- No replacement of plan-wave orchestration.

## Phases

### Phase 1 — MVP (done)

Detect + heuristic guidance inject for async/process; wire manager; tests; plan doc.

### Phase 1.5 — Graph-native rework (done)

- `supervisor` node in `plan_and_execute` after collect  
- On failed wave jobs → re-delegate same agent types with guided task  
- Caps via `subagent_supervisor_max_interventions`  
- Wave result merge + prior_job supersede so successes are kept  

### Related: Reflexion (main agent)

Main-agent Reflexion is implemented separately (`reflect_node`, meta-agent defaults on):

- `memory → meta → react ⇄ tools → reflect ⇄ react → finalize`
- Verbal self-feedback + LTM episodes; config `enable_self_refinement` / `enable_meta_agent`

### Phase 2

LLM diagnosis; richer `revise`; auto-extend steps once after successful guidance; optional terminate after exhausted interventions.

### Phase 3

Main tool `guide_subagent`; Studio panel; multi-job priority; optional OS-process supervisor.

## Test plan

- Unit: diagnosis classifiers (loop/thrash/hung/ok).  
- Unit: intervention caps / cooldown.  
- Integration-style: mock handle + bus receives guidance.  
- Regression: normal successful sub-agent not guided.

## Acceptance (MVP)

1. Spawned async sub-agent with simulated loop receives guidance message.  
2. At most `max_interventions` guidance messages per job.  
3. Healthy sub-agent with recent activity is not nudged.  
4. Feature can be disabled via config.
