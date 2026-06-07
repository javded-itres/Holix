# TUI

```bash
helix tui
helix tui -p myprofile

# В браузере (textual-serve; сессия на вкладку; нужен token)
uv sync --extra tui-web
helix tui --web
# URL http://127.0.0.1:8787/?token=... (если --token не задан — токен в консоли)

# LAN (полный доступ к агенту — задайте надёжный token)
helix tui --web --allow-lan --host 0.0.0.0 --port 8787 --token "$(openssl rand -hex 32)"
export HELIX_TUI_WEB_TOKEN="..."   # вместо --token
```

По умолчанию: **code-style** UI (`cli/tui/code/`).

Legacy dashboard: `HELIX_TUI_LEGACY=1 helix tui`

## Копирование

- **В чате:** выделите текст → кнопка **Copy** внизу (⌃C/⌘C не копируют последний ответ)
- **Окно копирования (F2 / `/open`):** `⌃C` / `⌘C` / `Ctrl+Shift+C` — выделение или весь транскрипт
- Slash: `/copy`, `/copy tool`, `/copy all` по-прежнему из чата

## Skill Hub

| Slash | Действие |
|-------|----------|
| `/hub` | Выбор каталога → поиск и установка |
| `/hub browse` | Браузер текущего каталога |
| `/hub installed` | Установленные hub-скиллы, плагины, MCP |

Подробнее: [HUB.md](HUB.md).