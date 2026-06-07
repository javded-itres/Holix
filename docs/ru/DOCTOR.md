# Helix Doctor

Диагностика профилей, LLM, gateway, Telegram и настроек безопасности.

## Использование

```bash
helix doctor              # только отчёт
helix doctor --fix        # фиксы + LLM для config.yaml
helix doctor --no-llm     # без LLM
helix -p work doctor
```

## Без `--fix`

- Ошибки, предупреждения, рекомендации
- Опционально план действий от LLM (если не `--no-advice`)

## С `--fix`

Детерминированные фиксы:

- Каталоги профиля, пути, stale gateway state, provider/model

LLM (default LLM профиля):

- Битый `config.yaml` (бэкап: `config.yaml.bak`)

## Проверки

- Запись в `~/.helix` (или `HELIX_HOME`)
- **Платформа:** ОС, путь данных, `node`/`npx`/`uv`/`git` в PATH; Windows: подсказка psutil, whitelist терминала
- YAML профиля и providers
- LLM endpoint и модель
- Gateway state / health
- Telegram token и allowlist
- Production: pepper, CORS, auth, code executor

После исправлений смотрите runtime-логи: `helix logs -l error` — [LOGS.md](LOGS.md).