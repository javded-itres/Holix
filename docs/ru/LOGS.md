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

Результаты агента — в `agent.jsonl` и в памяти разговора; cron может дублировать краткий итог в привязанную сессию TUI/Telegram.

## Команды `holix logs`

```bash
holix logs                          # последние 80 строк, все источники
holix logs show -n 200
holix logs -s agent                 # только agent.jsonl
holix logs -s gateway
holix logs -s cron -p work
holix logs -s subagent
holix logs -s system                # holix.log
holix logs -l error                 # ERROR и выше
holix logs -l warning
holix logs -g "Tool call"           # фильтр по тексту
holix logs -f                       # follow (как tail -f)
holix logs --debug -v
holix logs list                     # файлы и размеры
holix logs rotate
holix logs debug on|off|status
```

### Источник (`-s` / `--source`)

| Значение | Файлы |
|----------|--------|
| `all` | Все существующие (по умолчанию) |
| `agent` | `agent.jsonl`, `agent.debug.jsonl` |
| `gateway` | `gateway/gateway.log` |
| `cron` | `profiles/<profile>/data/cron/runs.log` |
| `subagent` | `subagent.jsonl` |
| `system` | `holix.log`, `hub-autoupdate.log` |

## Режим debug

По умолчанию выключен. При включении:

- Пишется `logs/agent.debug.jsonl`
- Debug субагентов дублируется туда
- Уровень root-логгера — `DEBUG`
- Состояние в `logs/logging.json` (сохраняется после перезапуска)

```bash
holix logs debug on
# или HOLIX_LOG_DEBUG=true в .env
```

CLI и `.env` комбинируются: достаточно одного источника.

## Ротация

| Переменная | По умолчанию | Назначение |
|------------|--------------|------------|
| `HOLIX_LOG_MAX_BYTES` | 10 MiB | Порог ротации |
| `HOLIX_LOG_BACKUP_COUNT` | 10 | Число backup-файлов |
| `HOLIX_LOG_ROTATION_DAYS` | 14 | Удаление старых backup |

```bash
holix logs rotate
holix logs rotate --no-purge
```

`holix.log` и `subagent.jsonl` используют `RotatingFileHandler`. `holix logs rotate` обрабатывает остальные файлы по размеру.

## Формат JSONL (агент)

Пример строки в `agent.jsonl`:

```json
{
  "timestamp": "2026-06-06T12:00:00+00:00",
  "level": "INFO",
  "category": "agent",
  "message": "Tool call completed: read_file",
  "tool": "read_file",
  "conversation_id": "tui_default",
  "event_type": "tool_call_result"
}
```

Фильтр: `holix logs -s agent -g conversation_id` или `-v`.

## Когда пишутся логи

- **CLI / TUI / `holix run`:** события через `wire_default_monitoring()` на `HolixAgent`
- **Gateway:** `gateway.log` при фоновом старте; agent JSONL при API-запусках
- **Cron:** `runs.log`; agent JSONL при выполнении задач
- **Субагенты:** `subagent.jsonl` при spawn/terminate

Инициализация при каждом вызове `holix` (`configure_holix_logging()` в `cli/main.py`).

## Диагностика

```bash
holix logs -l error -n 100
holix logs -s gateway -f
holix doctor
```

Если логов нет — выполните `holix run "hi"` или запустите gateway.

Windows: для надёжной остановки процессов — `uv sync --extra windows` (psutil).

## См. также

- [CLI.md](CLI.md)
- [GATEWAY.md](GATEWAY.md)
- [CONFIGURATION.md](CONFIGURATION.md) — `HOLIX_LOG_*`
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md)