# Браузерная автоматизация (Playwright)

Управление локальным Chromium через Playwright. **По умолчанию выключено**; нужен extra `browser`.

## Установка

```bash
uv sync --extra browser
uv run playwright install chromium
```

В `.env`:

```env
ENABLE_BROWSER_TOOLS=true
BROWSER_HEADLESS=true
BROWSER_ALLOWED_HOSTS=example.com
```

## Инструменты

| Инструмент | Риск | Назначение |
|------------|------|------------|
| `browser_open` | high | Открыть URL; `record=true` — сразу писать WebM |
| `browser_snapshot` | low | Снимок DOM с refs `e1`, `e2` |
| `browser_click` | high | Клик |
| `browser_fill` | high | Ввод текста |
| `browser_press` | medium | Клавиши |
| `browser_wait` | low | Ожидание |
| `browser_record_start` | medium | Начать запись видео сессии |
| `browser_record_stop` | low | Остановить запись и сохранить WebM (сессия остаётся) |
| `browser_close` | low | Закрыть сессию (при записи — финализирует видео) |

Сценарий: open → snapshot → fill/click → close.

Видео: `browser_record_start` (или `browser_open` + `record=true`) → действия → `browser_record_stop` / `browser_close`.  
Файлы: `{DATA_DIR}/browser_videos/*.webm`.

## Безопасность

- Только `http`/`https`
- Запрет localhost и private IP
- Allowlist: `BROWSER_ALLOWED_HOSTS`
- High-risk tools требуют подтверждения в TUI (`/yes`, `/1`, …)

Подробнее на английском (полная версия): [../en/BROWSER_TOOLS.md](../en/BROWSER_TOOLS.md).