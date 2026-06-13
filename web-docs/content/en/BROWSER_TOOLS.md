# Browser automation (Playwright)

Holix can control local Chromium via **Playwright**: open pages, snapshot interactive elements, click and type. **Disabled by default**; requires the `browser` extra.

## When to use

| Task | Approach |
|------|----------|
| Static pages, APIs, markdown | `web_fetch` / `web_search` |
| JS sites, forms, SPAs, login | `browser_*` tools |
| Debug screenshot | `browser_snapshot` with `screenshot: true` |

## Install

```bash
uv sync --extra browser
uv run playwright install chromium
```

Enable in `.env`:

```env
ENABLE_BROWSER_TOOLS=true
BROWSER_HEADLESS=true
BROWSER_VIEWPORT_WIDTH=1280
BROWSER_VIEWPORT_HEIGHT=720
BROWSER_ALLOWED_HOSTS=example.com,.mycompany.org
```

Or: `holix install --extra browser`

## Tools

| Tool | Risk | Description |
|------|------|-------------|
| `browser_open` | high | Open URL (`wait_until`: load / domcontentloaded / networkidle / commit) |
| `browser_snapshot` | low | Title, interactive elements with refs `e1`, `e2`, … |
| `browser_click` | high | Click by `ref` or CSS `selector` |
| `browser_fill` | high | Type into field |
| `browser_press` | medium | Key (Enter, Tab, Escape, …) |
| `browser_wait` | low | Wait for selector, timeout, or `network_idle` |
| `browser_close` | low | Close browser session for conversation |

Typical flow: `browser_open` → `browser_snapshot` → `browser_fill` / `browser_click` → `browser_close`.

Screenshots: `{DATA_DIR}/browser_screenshots/` when `screenshot=true`.

## Sessions

One Chromium session per `conversation_id`. Re-opening in the same chat reuses the context.

## Security

URL policy (`core/tools/browser/policy.py`):

- Only `http` / `https`
- Blocks `javascript:`, `file:`, `data:`, `blob:`, `about:`
- Blocks localhost, private IPs, `*.local`
- Optional allowlist: `BROWSER_ALLOWED_HOSTS`

High-risk tools respect the same confirmation flow as terminal commands in TUI (`/yes`, `/1`, …).

Production: set `ENABLE_BROWSER_TOOLS=false` unless required; use allowlists.

## Profile / gateway

Restart the agent session or run `holix gateway reload` after changing `.env`. Doctor warns if browser extra is missing but tools are enabled.