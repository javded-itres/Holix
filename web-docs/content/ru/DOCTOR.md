# Holix Doctor

Диагностика профилей, LLM, gateway, Telegram и настроек безопасности.

## Использование

```bash
holix doctor              # только отчёт
holix doctor --fix        # фиксы + LLM для config.yaml
holix doctor --no-llm     # без LLM; без проверки доступности endpoint (удобно в CI)
holix -p work doctor
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

- Запись в `~/.holix` (или `HOLIX_HOME`)
- **Платформа:** ОС, путь данных, `node`/`npx`/`uv`/`git` в PATH; Windows: подсказка psutil, whitelist терминала
- YAML профиля и providers
- LLM endpoint и модель (пропускается с `--no-llm`)
- Gateway state / health
- Telegram token, access requests и allowlist
- Production: pepper, CORS, auth, code executor

После исправлений смотрите runtime-логи: `holix logs -l error` — [LOGS.md](LOGS.md).