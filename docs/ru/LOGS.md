# Логи и наблюдаемость

Holix пишет структурированные логи в каталог данных. Команда **`holix logs`** — просмотр, фильтрация, ротация и режим debug.

## Каталог данных

| ОС | Путь по умолчанию |
|----|-------------------|
| Linux / macOS | `~/.holix/` |
| Windows | `%LOCALAPPDATA%\Holix\` |
| Переопределение | `HOLIX_HOME=/путь/к/данным` |
| Linux (XDG) | `$XDG_DATA_HOME/holix/` без `HOLIX_HOME` |

Логи: `{HOLIX_HOME}/logs/` (если не указано иное).

## Файлы логов

| Файл | Источник | Содержимое |
|------|----------|------------|
| `logs/agent.jsonl` | Агент | Вызовы tools, ошибки, ответы, навыки (JSONL) |
| `logs/agent.debug.jsonl` | Агент (debug) | То же при включённом debug |
| `logs/subagent.jsonl` | Субагенты | spawn / terminate |
| `logs/holix.log` | Система | Python root logger (с ротацией) |
| `gateway/gateway.log` | Gateway | Uvicorn / supervisor |
| `profiles/<p>/data/cron/runs.log` | Cron | Строки запусков задач |
| `logs/hub-autoupdate.log` | Hub | Автообновление каталога |
| `logs/history_<profile>.txt` | chat-command | История ввода (не вывод агента) |

Результаты работы агента — в `agent.jsonl` и в памяти разговора; cron может дублировать краткий итог в привязанную сессию TUI/Telegram.

## Команды `holix logs`

```bash
holix logs                          # последние 80 строк, все источники
holix logs show -n 200
holix logs -s agent                 # только agent.jsonl
holix logs -s gateway
holix logs -s cron -p work
holix logs -s subagent
holix logs -l error                 # ERROR и выше
holix logs -g "Tool call"           # фильтр по тексту
holix logs -f                       # follow (как tail -f)
holix logs list                     # файлы и размеры
holix logs rotate                   # ротация + очистка старых backup
holix logs debug on|off|status      # режим debug
```

Источники `-s`: `all`, `agent`, `gateway`, `cron`, `subagent`, `system`.

## Режим debug

По умолчанию выключен. При включении:

- Пишется `logs/agent.debug.jsonl`
- Уровень root-логгера — `DEBUG`
- Состояние в `logs/logging.json`

```bash
holix logs debug on
# или HOLIX_LOG_DEBUG=true в .env
```

## Ротация

| Переменная | По умолчанию | Назначение |
|------------|--------------|------------|
| `HOLIX_LOG_MAX_BYTES` | 10 MiB | Порог ротации |
| `HOLIX_LOG_BACKUP_COUNT` | 10 | Число backup-файлов |
| `HOLIX_LOG_ROTATION_DAYS` | 14 | Удаление старых backup |

```bash
holix logs rotate
```

## Диагностика

```bash
holix logs -l error -n 100
holix logs -s gateway -f
holix doctor
```

Windows: для надёжной остановки процессов — `uv sync --extra windows` (psutil).

## См. также

- [CLI.md](CLI.md)
- [GATEWAY.md](GATEWAY.md)
- [CONFIGURATION.md](CONFIGURATION.md)
- Полная версия: [../en/LOGS.md](../en/LOGS.md)