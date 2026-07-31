# Supervisor субагентов

Дизайн и поведение runtime + graph supervisor для застрявших sub-agent jobs.

Полная версия (EN): [SUBAGENT_SUPERVISOR.md](../en/SUBAGENT_SUPERVISOR.md).

## Кратко

| Уровень | Когда | Действие |
|---------|--------|----------|
| Runtime | job RUNNING, loop/hang/thrash | Guidance в тот же job |
| Graph | после collect в plan mode | Rework failed agent types |

Настройки: `HOLIX_SUBAGENT_SUPERVISOR_*` — см. [CONFIGURATION.md](CONFIGURATION.md), [SUBAGENTS.md](SUBAGENTS.md).

Связанные темы: [EXECUTION_MODES.md](EXECUTION_MODES.md) (Reflexion, step budget).
