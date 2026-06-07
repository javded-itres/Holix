# Архитектура

```
HelixAgent → run_agent_loop() (core/agent_execution.py)
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

Конфиг: `HelixRuntimeConfig` из профиля + `Settings` (.env).