# Архитектура

```
HolixAgent → run_agent_loop() (core/agent_execution.py)
           → LangGraph или fallback AgentLoop
```

| Слой | Путь |
|------|------|
| События | `core/agent_events.py` |
| DI | `core/di/`, Dishka |
| Инструменты | `core/tools/` |
| Память | `core/memory/` |
| API | `api/gateway.py` |
| CLI | `cli/main.py` |
| Supervisor gateway | `cli/services/supervisor.py` |
| Doctor | `cli/doctor/` |

Конфиг: `HolixRuntimeConfig` из профиля + `Settings` (.env).

**Идентичность профиля:** `SOUL.md` (личность агента, вставляется в каждую сессию), `USER.md` (факты о пользователе), `INIT.md` (онбординг до `complete_agent_initialization`). См. `core/profile/`, [PROFILES.md](PROFILES.md).