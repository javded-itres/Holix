# Documentation site moved

The Holix documentation website lives in a separate repository: **[holix-docs](../holix-docs)** (sibling directory) or [holix-agent.ru](https://holix-agent.ru).

Helix CLI resolves the site via:

1. `HOLIX_WEB_DOCS_DIR` environment variable
2. `../holix-docs` next to this repository
3. This legacy `web-docs/` folder (if present)

Commands:

```bash
holix docs          # serve site
holix docs build    # sync Helix/docs → holix-docs/content, rebuild index
```

To work on the site directly, use the holix-docs repository (`python build.py`, `python serve.py`).