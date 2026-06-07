# Решение проблем

## Gateway не стартует

```bash
helix doctor
helix gateway status
helix logs -s gateway -n 50
```

## Нет вывода агента / тихие ошибки

```bash
helix logs -l error -n 100
helix logs -s agent -f
helix logs debug on
```

## Windows

- Терминал: `dir`, `type`, `where` вместо `ls`, `cat`
- Субагенты — режим async
- Данные: `%LOCALAPPDATA%\Helix` или `HELIX_HOME`
- Опционально: `uv sync --extra windows`

## Ошибка Dishka / agent init

```bash
helix doctor --fix
```

## LLM недоступен

```bash
helix models setup
ollama serve
helix doctor
```

## Telegram access denied

Укажите `HELIX_TELEGRAM_ALLOWED_USERS` (числовой user id).

## API 401

Заголовок `Authorization: Bearer <key>` или `X-API-Key`. Admin key — через `/admin/api-keys`.

## См. также

- [LOGS.md](LOGS.md) — файлы логов, фильтры, ротация, debug