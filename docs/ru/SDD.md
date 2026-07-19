# Spec-Driven Development (SDD) в Holix

Модель [OpenSpec](https://github.com/javded-itres/OpenSpec): сначала спецификация, потом реализация, после завершения — merge в main specs.

План внедрения: [SDD_STUDIO_PLAN.md](SDD_STUDIO_PLAN.md).

## Дерево в workspace

```text
openspec/
  config.yaml
  specs/<domain>/spec.md      # source of truth
  changes/<change-id>/
    proposal.md
    design.md
    tasks.md                  # checklist + assignee
    specs/<domain>/spec.md    # delta ADDED/MODIFIED/REMOVED
    .apply-mode               # self | subagents | hybrid
  changes/archive/YYYY-MM-DD-<id>/
```

## Agent tools

| Tool | Назначение |
|------|------------|
| `sdd_init` | Scaffold `openspec/` |
| `sdd_list_specs` / `sdd_read_spec` | Main specs |
| `sdd_create_change` / `sdd_write_artifact` | Propose |
| `sdd_set_task_assignee` / `sdd_check_task` | Tasks |
| `sdd_request_apply_mode` / `sdd_set_apply_mode` | Pre-apply gate |
| `sdd_apply` | Plan task → executor |
| `sdd_dispatch` | Spawn subagents for non-main tasks |
| `sdd_archive` | Merge deltas + archive |

## Slash

```
/spec
/spec init
/spec propose <change-id>
/spec status [change-id]
/spec mode <change-id> self|subagents|hybrid
/spec apply <change-id>
/spec archive <change-id>
```

## Skills

- `holix-sdd-propose`
- `holix-sdd-apply`
- `holix-sdd-archive`

## Studio

- Tab **Specs** — domains, changes, tasks, apply mode, apply/archive
- API: `/studio/api/sdd/*` (feature `agent.sdd`)
- Soft gate: `write_file` warns if apply-ready change has no mode

## Workflow

1. Read main specs → create change → fill proposal / delta specs / tasks **with assignee**
2. User chooses **self | subagents | hybrid**
3. `sdd_apply` → optionally `sdd_dispatch` → implement → `sdd_check_task`
4. `sdd_archive` merges into `openspec/specs/`
