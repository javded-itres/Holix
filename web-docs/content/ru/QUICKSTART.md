# Быстрый старт

```bash
uv sync
helix doctor
helix run "Привет"
helix tui
helix gateway start
helix gateway status
helix logs -l error          # ошибки runtime
helix doctor --fix   # починка конфига (через default LLM)
```

Опционально:

```bash
uv sync --extra telegram
export TELEGRAM_BOT_TOKEN=...
helix gateway start   # API + Telegram
```