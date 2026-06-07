# Логи и наблюдаемость

Helix пишет структурированные логи в каталог данных. Команда **`helix logs`** — просмотр, фильтрация, ротация и режим debug.

## Каталог данных

| ОС | Путь по умолчанию |
|----|-------------------|
| Linux / macOS | `~/.helix/` |
| Windows | `%LOCALAPPDATA%\Helix\` |
| Переопределение | `HELIX_HOME=/путь/к/данным` |
| Linux (XDG) | `$XDG_DATA_HOME/helix/` без `HELIX_HOME` |

Логи: `{HELIX_HOME}/logs/` (если не указано иное).

## Файлы логов

| Файл | Источник | Содержимое |
|------|----------|------------|
| `logs/agent.jsonl` | Агент | Вызовы tools, ошибки, ответы, навыки (JSONL) |
| `logs/agent.debug.jsonl` | Агент (debug) | То же при включённом debug |
| `logs/subagent.jsonl` | Субагенты | spawn / terminate |
| `logs/helix.log` | Система | Python root logger (с ротацией) |
| `gateway/gateway.log` | Gateway | Uvicorn / supervisor |
| `profiles/<p>/data/cron/runs.log` | Cron | Строки запусков задач |
| `logs/hub-autoupdate.log` | Hub | Автообновление каталога |
| `logs/history_<profile>.txt` | chat-command | История ввода (не вывод агента) |

Результаты работы агента — в `agent.jsonl` и в памяти разговора; cron может дублировать краткий итог в привязанную сессию TUI/Telegram.

## Команды `helix logs`

```bash
helix logs                          # последние 80 строк, все источники
helix logs show -n 200
helix logs -s agent                 # только agent.jsonl
helix logs -s gateway
helix logs -s cron -p work
helix logs -s subagent
helix logs -l error                 # ERROR и выше
helix logs -g "Tool call"           # фильтр по тексту
helix logs -f                       # follow (как tail -f)
helix logs list                     # файлы и размеры
helix logs rotate                   # ротация + очистка старых backup
helix logs debug on|off|status      # режим debug
```

Источники `-s`: `all`, `agent`, `gateway`, `cron`, `subagent`, `system`.

## Режим debug

По умолчанию выключен. При включении:

- Пишется `logs/agent.debug.jsonl`
- Уровень root-логгера — `DEBUG`
- Состояние в `logs/logging.json`

```bash
helix logs debug on
# или HELIX_LOG_DEBUG=true в .env
```

## Ротация

| Переменная | По умолчанию | Назначение |
|------------|--------------|------------|
| `HELIX_LOG_MAX_BYTES` | 10 MiB | Порог ротации |
| `HELIX_LOG_BACKUP_COUNT` | 10 | Число backup-файлов |
| `HELIX_LOG_ROTATION_DAYS` | 14 | Удаление старых backup |

```bash
helix logs rotate
```

## Диагностика

```bash
helix logs -l error -n 100
helix logs -s gateway -f
helix doctor
```

Windows: для надёжной остановки процессов — `uv sync --extra windows` (psutil).

## См. также

- [CLI.md](CLI.md)
- [GATEWAY.md](GATEWAY.md)
- [CONFIGURATION.md](CONFIGURATION.md)
- Полная версия: [../en/LOGS.md](../en/LOGS.md)