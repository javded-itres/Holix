# Holix development rules

Обязательные подходы и паттерны для разработки **Holix** (agent core, gateway, CLI) и экосистемы (extensions, deploy).  
Нарушение архитектурных правил ломает CI (`tests/test_architecture_boundaries.py`) и прод-безопасность.

Связанные документы: [CONTRIBUTING.md](CONTRIBUTING.md) · [docs/en/ARCHITECTURE.md](docs/en/ARCHITECTURE.md) · [docs/en/EXTENSIONS.md](docs/en/EXTENSIONS.md) · [docs/en/SECURITY.md](docs/en/SECURITY.md) · [AGENTS.md](AGENTS.md)

---

## 1. Принципы (non‑negotiable)

| # | Правило |
|---|--------|
| 1 | **Core = runtime, не продукт.** Бизнес-фичи (billing, Studio, prometheus, user-settings) — **отдельные пакеты/репозитории**, не `core/`. |
| 2 | **Dependency direction:** `cli` / `api` / `integrations` → `core`. **Никогда** `core` → `cli` \| `api` \| `integrations`. |
| 3 | **Профиль — единица данных.** Секреты, memory, workspace, skills — только под `HOLIX_HOME/profiles/<name>/`, не в git. |
| 4 | **События, не UI-хаки.** UI (TUI, Telegram, MAX, Studio) подписывается на `AgentEventBus`, не лезет внутрь loop. |
| 5 | **Безопасность по умолчанию.** Whitelist terminal, jail, confirmations, secrets path guard — не отключать «для удобства» без явного ops-решения. |
| 6 | **Прод только через GitHub Actions** (`holix-billing-deploy` / `holix-studio-deploy`). Нет ручных rsync/hotfix без approval в **текущем** чате. |
| 7 | **Тесты и ruff обязательны** для merge в `main`. Релиз = версия + CHANGELOG + tag `vX.Y.Z`. |

---

## 2. Архитектура слоёв

```
cli / api / integrations     presentation (UX, HTTP, messengers)
        │
        ▼
core/application, core/di    application (run scope, Dishka)
        │
        ▼
core/* (graph, tools, …)     domain + infrastructure runtime
```

### Обязательные паттерны

| Область | Паттерн | Где |
|---------|---------|-----|
| Агент | `HolixAgent` + LangGraph modes (`react` / `hybrid` / `plan_and_execute`) | `core/agent.py`, `core/graph/` |
| Наблюдаемость | `AgentEvent` → bus → TUI / gateway / metrics / messengers | `core/agent_events.py` |
| Инструменты | subclass `BaseTool`, регистрация в registry | `core/tools/` |
| Конфиг | Settings (`.env`) + profile `config.yaml` + CLI flags | `config.py`, `core/profile/` |
| DI | Dishka: agent construction, gateway APP scope | `core/di/` |
| Плагины outer | `core.plugins` hooks из `integrations.bootstrap` | не import integrations из core |

### Запрещено

- Импорт `cli.*` / `api.*` / `integrations.*` из `core.*`
- Хранить user secrets, API keys, `.env` профилей в репозитории
- Дублировать agent loop в Telegram/MAX — только host + events
- «Временно» копировать product-код в monorepo Holix вместо extension

---

## 3. Профили и workspace

```text
$HOLIX_HOME/profiles/<name>/
  .env              # секреты и feature flags (не в git)
  config.yaml       # model, workspace_root, jail, …
  workspace/        # файлы пользователя (jail root)
  data/             # memory, skills, bg processes, extensions data
  SOUL.md / USER.md # личность / факты о пользователе
```

### Обязательно

| Тема | Правило |
|------|---------|
| Workspace jail | Обычные user-профили: `workspace_jail_enabled: true`. Ops/admin/production могут `false` — **осознанно**. |
| Свой workspace при jail off | Команды в `…/profiles/<name>/workspace` разрешены; `.env`, чужие профили, caches — **всегда** blocked. |
| Terminal whitelist | Allowlist опционален; **destructive patterns** (`rm -rf`, `curl\|sh`, …) **всегда** on. |
| Пути | Relative path tools/plans → `workspace_root` / execution context, **не** CWD процесса (Studio install dir). |
| Identity | `SOUL.md` pin system; `USER.md` merge; не класть секреты в SOUL. |

---

## 4. Agent loop, tools, honesty

### Tools

1. Долгоживущие процессы (bots, `uvicorn`, `npm run dev`) → **`start_background_process`**, не `run_terminal` + `nohup`.
2. Background index (`background_processes.json`) — running **и** stopped history (restart после reboot).
3. Не поднимать второй long-poll Telegram на том же bot token, что holix-gateway.
4. High-risk tools → confirmation flow (`core/security/confirmation.py`).

### Model / pipeline

| Паттерн | Правило |
|---------|---------|
| Pipeline | `classic` (тихий UX ≈1.0.2) vs `modern` (anti-monologue honesty); default classic на prod messengers. |
| Action without tools | Нельзя завершать ход на «сделаю/создаю/запускаю…» без tool calls — force tools / honesty nudge. |
| Monologue spam | Collapse pathological repetition; stream abort; не красить status monologue в live UI. |
| Truncation | `finish_reason=length` не считается «задачей выполнена» (modern). |
| Tokens | Usage → `LLMCallCompletedEvent` (Studio metering); не глотать ошибки emit. |

### Skills / SDD

- Skills: markdown + hub; self-improve только после осмысленного success.
- SDD archive: merge delta → main `openspec/specs` **до** move change; без mergeable requirements — **refuse** (кроме `force`).

---

## 5. Extensions (обязательный путь для продуктов)

**Не форкать Holix**, чтобы добавить billing / metrics / miniapp / Studio-фичу.

| Тип | Entry point | Хуки |
|-----|-------------|------|
| Host | `holix.extensions` | `mount_gateway`, `register_cli`, `register_telegram` / `register_max`, `on_startup` |
| Agent | `holix.agent.extensions` | tools, slash, middleware, system prompt, settings |
| Drop-in | `$HOLIX_HOME/extensions/<name>/` | `extension.py` / `agent.py` / `holix.plugin.json` |

### Обязательные паттерны extension

1. Зависимость: **`holix-sdk`** (+ Holix runtime). Host **не** импортирует `core.*` / `cli.*` (agent tools — исключение через Holix/BaseTool).
2. Минимальные `permissions` в коде и `holix.plugin.json` (`gateway`, `middleware`, `tools`, …).
3. Settings: `default_settings` + profile file; feature flag `enabled: false` по умолчанию для risky sidecars.
4. Deploy layout prod:
   ```text
   /opt/holix-extensions/<name>/     ← git checkout
   /var/lib/holix/extensions/<name>  → symlink
   /opt/holix/.venv                  ← uv pip install --no-deps -e
   ```
5. Референс: `packages/holix-extension-demo`, [holix-prometheus](https://github.com/javded-itres/holix-prometheus), billing extensions.

---

## 6. Security

### Terminal

```
whitelist? ──yes──► allowlist + dangerous patterns
         └──no───► dangerous patterns only
+ secrets path guard (profiles, .env, memory-cache)
+ workspace jail (if enabled)
+ confirmation for high-risk tools
```

### Secrets

- Никогда не логировать полные `TELEGRAM_BOT_TOKEN`, API keys, vault keys.
- Profile secrets path access blocked even with jail off.
- Production: `HOLIX_REQUIRE_AUTH=true`, pepper, CORS explicit, gateway `127.0.0.1` + TLS proxy.

### Confirmations

- User deny → `confirmation_deny` metrics / audit; не обходить UI confirm из agent code.

---

## 7. Messengers (Telegram / MAX)

| Правило | Детали |
|---------|--------|
| Один poller на token | Только `integrations.telegram.main` / gateway companion |
| Admin routing | `HOLIX_TELEGRAM_ADMIN_PROFILE` + admin user id → отдельный profile |
| Billing / menus | Host extensions, не hardcode в core |
| Live UI | Status monologue не в answer buffer; final через `resolve_messenger_final_content` + sanitize |
| Locale | EN + RU docs/i18n при user-facing strings |

---

## 8. Deploy & release

### Production (VDS)

| До | После |
|----|--------|
| Код | **только** GHA `holix-billing-deploy` / studio-deploy, branch `main` (или явный ref) |
| Ручной rsync/hotfix | **запрещён** без approval в текущем turn (см. AGENTS.md) |
| Profile `.env` | Source of truth = GitHub Secrets/Variables (render-runtime-env); исключения: server-owned tariffs |
| Extensions | `install-extensions.sh` + editable venv; feature flags в env |

Layout:

```text
/opt/holix-billing/      deploy scripts
/opt/holix/              Holix + .venv
/opt/holix-extensions/   extension checkouts
/var/lib/holix/          HOLIX_HOME
```

### Release Holix package

1. Изменения на `main` + CI green.
2. Branch `release/X.Y.Z`: bump `pyproject.toml` + `cli/__init__.py` + `docs/CHANGELOG.md`.
3. PR → CI (ruff, pytest multi-OS) → merge.
4. Tag `vX.Y.Z` → workflows **GitHub Release** + **Publish to PyPI**.
5. Tag **должен** совпадать с version в pyproject.

### Git hygiene

- Focused commits; no secrets in history.
- Не коммитить `node_modules/`, локальные `.env`, `presentations/` без нужды.
- Bilingual docs: user-facing CLI/config → `docs/en/` **и** `docs/ru/`.

---

## 9. Code style & tests

| Тема | Правило |
|------|---------|
| Python | **3.12+**, async-first agent paths |
| Lint | `ruff check` (I001 imports, F401, …) |
| Tests | `pytest`; behavior changes → new/updated tests; `-m "not llm"` для локали без API |
| Boundaries | `tests/test_architecture_boundaries.py` must pass |
| Naming | Holix (product), not Helix package name on PyPI (`Holix` / CLI `holix`) |

---

## 10. Checklist перед PR

- [ ] Нет `core` → outer imports
- [ ] Нет секретов в diff
- [ ] Product feature? → extension, не core (если не runtime-инфра)
- [ ] Terminal/long jobs: bg process API, не nohup
- [ ] Jail / secrets / destructive patterns не ослаблены случайно
- [ ] Tests + ruff green
- [ ] Docs EN/RU при user-facing change
- [ ] CHANGELOG entry при user-visible fix/feat (перед релизом)

---

## 11. Быстрые антипаттерны

| Антипаттерн | Правильно |
|-------------|-----------|
| Billing / metrics / miniapp в `core/` | Отдельный repo + entry points |
| `nohup python bot.py` из terminal | `start_background_process` |
| Второй getUpdates на token gateway | Запрет / другой token |
| Archive SDD без merge в main specs | Merge first, then move |
| Whitelist off = «всё можно» | Off only allowlist; destructive still blocked |
| Hotfix prod scp | GHA deploy only |
| Plan path via `cwd` Studio | `workspace_root` resolve |
| Monologue 18KB как final | Collapse + honesty + tools |

---

## 12. Где что лежит

| Задача | Путь |
|--------|------|
| Agent loop / graph | `core/graph/`, `core/agent.py` |
| Tools | `core/tools/` |
| Security / terminal | `core/security/`, `core/tools/terminal.py` |
| Profiles | `core/profile/`, `$HOLIX_HOME/profiles/` |
| Gateway | `api/gateway.py`, `api/routers/` |
| Messengers | `integrations/telegram/`, `integrations/max/` |
| Extension loader | `core/extensions/` |
| Deploy prod | `javded-itres/holix-billing-deploy` |
| Public SDK | `javded-itres/holix-sdk` |

---

*Документ для людей и coding-агентов. При конфликте с кодом — код + architecture tests; обновляйте RULES.md в том же PR.*
