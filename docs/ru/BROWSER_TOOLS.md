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
| `browser_open` | high | Открыть URL |
| `browser_snapshot` | low | Снимок DOM с refs `e1`, `e2` |
| `browser_click` | high | Клик |
| `browser_fill` | high | Ввод текста |
| `browser_press` | medium | Клавиши |
| `browser_wait` | low | Ожидание |
| `browser_close` | low | Закрыть сессию |

Сценарий: open → snapshot → fill/click → close.

## Безопасность

- Только `http`/`https`
- Запрет localhost и private IP
- Allowlist: `BROWSER_ALLOWED_HOSTS`
- High-risk tools требуют подтверждения в TUI (`/yes`, `/1`, …)

Подробнее на английском (полная версия): [../en/BROWSER_TOOLS.md](../en/BROWSER_TOOLS.md).