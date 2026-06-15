# Запуск внешних CLI (`holix launch`)

Запуск сторонних coding-агентов (Claude Code, OpenCode, Grok Build, …) в **tmux** с учётными данными LLM из **профиля Holix**. Только Linux и macOS.

## Требования

- **tmux** — `brew install tmux` или `apt install tmux`
- **Профиль Holix** с настроенной моделью — `holix models setup -p <профиль>`
- Установленный бинарник агента (или автоустановка через `holix launch setup`)

```bash
holix launch list           # поддерживаемые CLI и привязки
holix launch setup          # установка и привязка к профилю
holix launch claude         # открыть Claude Code в tmux
holix launch claude status  # привязка, модель, env, сессии
```

---

## Поддерживаемые агенты

| ID | Название | Подключение модели | Автоустановка |
|----|----------|-------------------|---------------|
| `claude` | Claude Code | `ANTHROPIC_*` + опции LiteLLM gateway | `npm install -g @anthropic-ai/claude-code` |
| `opencode` | OpenCode | `OPENCODE_CONFIG` → `opencode.json` Holix (`holix/<модель>`) | `curl … opencode.ai/install \| bash` |
| `grok-build` | Grok Build | `GROK_HOME` → `config.toml` Holix + `-m <модель>` | `curl … x.ai/cli/install.sh \| bash` |
| `gigacode` | GigaCode | `GIGACODE_*` + fallback `OPENAI_*` | вручную |
| `aider` | Aider | `OPENAI_*` / `LLM_MODEL` | `uv tool install aider-chat` |

> **Codex CLI и Codex App** (`codex`, `codex-app`) временно отключены в этой версии.

Слот модели по умолчанию для coding-агентов: **`coder`** (настраивается в `holix models setup` или в `holix launch setup`).

---

## Быстрый старт

```bash
# 1. Настроить LLM в профиле Holix
holix models setup -p default

# 2. Привязать внешние CLI к профилю
holix launch setup

# 3. Открыть агента (переиспользует последнюю живую сессию)
holix launch claude
holix launch opencode -t "почини падающие тесты"
holix launch grok-build --detach -t "рефакторинг auth"

# 4. Проверить привязку и переменные окружения
holix launch opencode status
```

### Подкоманды для каждого агента

Каждый CLI — отдельное приложение Typer: `holix launch <id>`:

| Вызов | Действие |
|-------|----------|
| `holix launch <id>` | Открыть CLI в tmux (attach или существующая сессия) |
| `holix launch <id> status` | Привязка, модель, env, активные сессии |

Общие опции `holix launch <id>`:

| Опция | Кратко | Описание |
|-------|--------|----------|
| `--cwd` | `-C` | Рабочая директория |
| `--task` | `-t` | Начальный промпт (в argv, где поддерживается) |
| `--model-slot` | `-m` | Слот модели профиля (`main`, `coder`, …) |
| `--detach` | | Запуск в фоне без attach |
| `--new` | `-n` | Всегда новая tmux-сессия |
| `--window` | `-w` | Новое окно в существующей сессии |
| `--session` | `-s` | Целевая tmux-сессия для `--window` |

---

## Мастер настройки

```bash
holix launch setup
holix launch setup -y    # без вопросов: включить все установленные CLI
```

Мастер:

1. Показывает список CLI и статус установки
2. Предлагает **автоустановку**, если есть `install_commands` (OpenCode, Grok Build, Claude, Aider)
3. Ищет бинарники в типичных путях (`~/.opencode/bin`, `~/.grok/bin`, …) до обновления PATH
4. Для каждого включённого CLI спрашивает:
   - **Слот модели** — какой слот профиля питает внешний CLI (`coder` по умолчанию)
   - **Назначить субагенту** — какой тип субагента Holix может запускать этот CLI через tool `external_cli` (`coder`, `researcher`, …)
5. Сохраняет привязки в `~/.holix/profiles/<профиль>/external_clis/bindings.json`

Пример привязки:

```json
{
  "bindings": [
    {
      "cli_id": "claude",
      "enabled": true,
      "command": "/usr/local/bin/claude",
      "model_slot": "coder",
      "agent_slot": "coder",
      "default_cwd": "/path/to/project"
    }
  ]
}
```

Только назначенный тип субагента с `enabled: true` может вызывать `external_cli` для этого CLI. Ручной `holix launch claude` из терминала не ограничен.

---

## Управление сессиями

| Команда | Описание |
|---------|----------|
| `holix launch sessions` | Сессии Holix для этого профиля |
| `holix launch tmux` | Все tmux-сессии на машине |
| `holix launch attach <id\|имя_tmux>` | Подключиться (`Ctrl+b d` — отсоединиться) |
| `holix launch send <id> "промпт"` | Отправить текст + Enter |
| `holix launch chat <id>` | Интерактивный relay (текст + стрелки для меню) |
| `holix launch output <id>` | Вывод панели (`-n` строк) |
| `holix launch kill <id>` | Остановить tmux-сессию |

Идентификатор: короткий id Holix или имя tmux (`holix-<профиль>-<cli>-<суффикс>`).

---

## Подключение моделей по агентам

Holix берёт модель из слота профиля (по умолчанию `coder`) и передаёт её в формате, который ожидает каждый CLI.

### Claude Code (`claude`)

- Env: `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL` (для gateway убирается хвост `/v1`)
- LiteLLM / кастомные шлюзы: `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1`, `ANTHROPIC_CUSTOM_MODEL_OPTION` для нестандартных id (например `coder`)

### OpenCode (`opencode`)

OpenCode **не** читает только `OPENAI_BASE_URL`. Holix создаёт:

```
~/.holix/profiles/<профиль>/opencode/opencode.json
```

и выставляет `OPENCODE_CONFIG`. В конфиге провайдер `holix` (`@ai-sdk/openai-compatible`), ваш `base_url`, ключ и модель `holix/<id>`. Запуск: `-m holix/<id>`.

### Grok Build (`grok-build`)

Holix создаёт:

```
~/.holix/profiles/<профиль>/grok/config.toml
```

с секцией `[model.<имя>]`, выставляет `GROK_HOME`, `XAI_API_KEY`, `GROK_MODELS_BASE_URL`. Задача передаётся **позиционным аргументом** (`grok -m coder "задача"`). При наличии — симлинк на `~/.grok/auth.json`.

### Aider / GigaCode

Стандартные переменные: `OPENAI_*` (Aider); `GIGACODE_*` + OpenAI fallback (GigaCode).

---

## Интерактивный relay (`holix launch chat`)

Когда внешний CLI показывает меню выбора (разрешения, модель, пункты 1–9):

- Обычный ввод текста
- **Стрелки**, Tab, Escape пробрасываются в tmux
- Цифры `1`–`9` без текста — быстрый выбор
- `Ctrl+C` выходит из relay (tmux-сессия остаётся)

---

## Пути в профиле

| Путь | Содержимое |
|------|------------|
| `~/.holix/profiles/<p>/external_clis/bindings.json` | `enabled`, путь к бинарнику, `model_slot`, `agent_slot`, cwd |
| `~/.holix/profiles/<p>/external_clis/sessions.json` | Активные сессии launch |
| `~/.holix/profiles/<p>/opencode/opencode.json` | Конфиг OpenCode (при запуске) |
| `~/.holix/profiles/<p>/grok/config.toml` | Конфиг Grok Build (при запуске) |

---

## Инструмент агента (`external_cli`)

**Назначенные субагенты** могут запускать и писать во внешние CLI через tool `external_cli` (`launch`, `send`, `output`, `list_sessions`). Те же модели профиля и tmux-сессии, что и в CLI.

**Правила доступа:**

| Кто вызывает | Может использовать `external_cli`? |
|--------------|-----------------------------------|
| Главный агент | Нет — tool скрыт у главного агента |
| Субагент без назначения | Нет |
| Субагент с `agent_slot` и `enabled: true` | Да — tool добавляется в список инструментов субагента |

Типовой сценарий:

```
Главный агент → delegate_to_subagent(coder, "рефакторинг auth в Claude Code")
Субагент coder → external_cli(action=launch, cli_id=claude, task="…")
```

Назначение настраивается в `holix launch setup` (поле **Назначить субагенту**) или в TUI:

```text
/launch        # модальное окно: назначить / снять субагента для CLI
/launch list   # список назначений в транскрипте
```

См. [LAUNCH_SUBAGENTS.md](LAUNCH_SUBAGENTS.md).

---

## Устранение неполадок

| Симптом | Что проверить |
|---------|---------------|
| `tmux is required` | Установите tmux |
| `Binary not found` | `holix launch setup` или ручная установка; мастер ищет `~/.opencode/bin`, `~/.grok/bin` |
| OpenCode не видит модель Holix | `holix launch opencode status` — нужны `OPENCODE_CONFIG` и `holix/...` |
| Задача не уходит в Grok | Используйте `-t`; задача в argv: `grok -m coder "задача"` |
| Ошибка модели `coder` в Claude | Base URL gateway без `/v1` — Holix нормализует сам |

---

## См. также

- [LAUNCH_SUBAGENTS.md](LAUNCH_SUBAGENTS.md) — субагенты Holix и `holix launch`
- [CLI.md](CLI.md) — справочник `holix`
- [PROFILES.md](PROFILES.md) — профили и слоты моделей
- [CONFIGURATION.md](CONFIGURATION.md) — провайдеры и `agent_models`