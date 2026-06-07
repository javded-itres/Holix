# Браузерная автоматизация (Playwright)

Helix может управлять локальным Chromium через **Playwright**: открывать страницы, получать снимок интерактивных элементов и выполнять клики/ввод. Функция **выключена по умолчанию** и требует отдельной установки зависимостей.

## Когда использовать

| Задача | Подход |
|--------|--------|
| Статическая страница, API, markdown | `web_fetch` / `web_search` |
| JS-сайт, формы, SPA, логин | **browser_*** инструменты |
| Скриншот для отладки | `browser_snapshot` с `screenshot: true` |

## Установка

```bash
# Зависимости Helix + Playwright
uv sync --extra browser

# Бинарник Chromium (один раз на машину)
uv run playwright install chromium
```

Проверка:

```bash
uv run python -c "from playwright.async_api import async_playwright; print('ok')"
```

## Включение

В `.env` или переменных окружения:

```env
ENABLE_BROWSER_TOOLS=true
BROWSER_HEADLESS=true
BROWSER_VIEWPORT_WIDTH=1280
BROWSER_VIEWPORT_HEIGHT=720
# Опционально: только эти хосты (через запятую). Пусто = без allowlist.
BROWSER_ALLOWED_HOSTS=example.com,.mycompany.org
```

После перезапуска агента в списке инструментов появятся `browser_*` (см. `helix` → `tools` или TUI).

## Инструменты

| Инструмент | Риск | Описание |
|------------|------|----------|
| `browser_open` | high | Открыть URL (`wait_until`: load / domcontentloaded / networkidle / commit) |
| `browser_snapshot` | low | URL, title, интерактивные элементы с refs `e1`, `e2`, … |
| `browser_click` | high | Клик по `ref` из snapshot или CSS `selector` |
| `browser_fill` | high | Ввод текста в поле по `ref` / `selector` |
| `browser_press` | medium | Клавиша (Enter, Tab, Escape, …) |
| `browser_wait` | low | Ожидание селектора, таймаут (мс) или `network_idle` |
| `browser_close` | low | Закрыть сессию браузера для текущего разговора |

### Типичный сценарий агента

1. `browser_open` → `https://app.example.com/login`
2. `browser_snapshot` → в ответе строки вида `[e3] textbox "Email"`
3. `browser_fill` → `ref=e3`, `text=user@example.com`
4. `browser_click` → `ref=e5` (кнопка Submit)
5. `browser_wait` → `network_idle: true` при необходимости
6. `browser_close` — по завершении задачи

Скриншоты сохраняются в `{DATA_DIR}/browser_screenshots/` при `browser_snapshot(screenshot=true)`.

## Сессии

- Одна сессия Chromium **на `conversation_id`** (чат / TUI / API).
- `ToolRegistry.execute()` прокидывает id через `core/tools/execution_context.py`.
- Повторный `browser_open` в том же чате переиспользует контекст и переходит на новый URL.

## Безопасность

**URL policy** (`core/tools/browser/policy.py`):

- Только `http` / `https`
- Запрещены: `javascript:`, `file:`, `data:`, `blob:`, `about:`
- Запрещены `localhost`, `*.local`, private/reserved IP
- Опциональный allowlist: `BROWSER_ALLOWED_HOSTS`

**Подтверждения:** `browser_open`, `browser_click`, `browser_fill` имеют `risk_level=high` и проходят через `ActionGuard` (как `terminal` / `write_file`). В non-interactive режиме HIGH без grant будет отклонён.

## Архитектура

```
ToolRegistry.execute(conversation_id)
    → conversation_scope(conversation_id)
    → browser_* tool
        → BrowserSessionManager.get_or_create(conversation_id)
        → Playwright chromium (headless по умолчанию)
```

Код: `core/tools/browser/` — `session.py`, `snapshot.py`, `policy.py`, `tools.py`.  
Регистрация: `core/tools/registry.py` при `enable_browser_tools=True`.

## Тесты

```bash
uv run pytest tests/test_browser_tools.py -q
```

Тесты мокают Playwright; реальный браузер в CI не нужен.

## Устранение неполадок

| Симптом | Решение |
|---------|---------|
| `Playwright is not installed` | `uv sync --extra browser && playwright install chromium` |
| Инструментов `browser_*` нет | `ENABLE_BROWSER_TOOLS=true`, перезапуск |
| `Host '…' is not in browser_allowed_hosts` | Добавить хост в `BROWSER_ALLOWED_HOSTS` или очистить allowlist |
| `localhost is not allowed` | Ожидаемо; используйте публичный URL или туннель |
| `Unknown ref 'e9'` | Снова вызвать `browser_snapshot` после изменения DOM |
| Подтверждение блокирует действие | Разрешить в TUI или понизить риск через grants / `AUTO_ALLOW_THRESHOLD` (осторожно) |

## Связанные документы

- [architecture.md](../architecture.md) — общая архитектура агента
- [refactoring-plan.md](../refactoring-plan.md) — рефакторинг runtime (ветка `refactor/unified-runtime`)
- [TROUBLESHOOTING.md](../TROUBLESHOOTING.md) — общие проблемы Helix