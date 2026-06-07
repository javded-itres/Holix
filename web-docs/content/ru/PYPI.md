# Публикация на PyPI

Руководство по выпуску пакета **Helix** на [PyPI](https://pypi.org).

## Имя пакета

На PyPI проект публикуется как **`helix-agent-ai`** (HelixAgentAi; имена `helix` и `helix-agent` заняты другими проектами).

```bash
pip install helix-agent-ai
pip install "helix-agent-ai[telegram,browser]"
pip install "helix-agent-ai[all]"
```

Команда в терминале по-прежнему: **`helix`**.

## Что нужно сделать

### 1. Аккаунт и имя

- Регистрация на [pypi.org](https://pypi.org/account/register/)
- Проверить, что `helix-agent-ai` свободен
- API-токен или Trusted Publishing с GitHub

### 2. Метаданные (уже в репозитории)

- `pyproject.toml` — `name = "helix-agent-ai"`, зависимости, extras, `license-files`
- `config.py` включён в wheel (обязательно для `from config import settings`)
- `[project.scripts]` → `helix`

### 3. Перед каждым релизом

1. Поднять версию в `pyproject.toml` и `cli/__init__.py`
2. `uv build` — без ошибок
3. Проверить установку wheel в чистом venv Python 3.14
4. `uv run pytest -m "not llm"`
5. Обновить `docs/CHANGELOG.md`
6. Тег `v0.1.0`

### 4. Сборка и загрузка

PyPI **не принимает пароль аккаунта** — нужен **API token** (`pypi-...`).

```bash
export UV_PUBLISH_TOKEN='pypi-AgENdXNlcm5hbWU6...'   # pypi.org → API tokens
uv sync --group dev
uv build
# тест TestPyPI:
uv publish --publish-url https://test.pypi.org/legacy/ dist/*
# прод:
uv publish dist/*
```

Не вводите пароль от аккаунта при запросе `uv` — будет `403 Username/Password authentication is no longer supported`.

### 5. Документация для пользователей

После публикации обновить [INSTALLATION.md](INSTALLATION.md) и README: `pip install helix-agent-ai`.

## Ограничения

- Только **Python 3.14+**
- Тяжёлые зависимости (ChromaDB, LangGraph)
- Для browser: после pip — `playwright install chromium`

Полная английская версия: [../en/PYPI.md](../en/PYPI.md).