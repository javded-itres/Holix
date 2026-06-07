# Публикация на PyPI

Руководство по выпуску пакета **Helix** на [PyPI](https://pypi.org).

## Имя пакета

На PyPI проект публикуется как **`helix-agent`** (имя `helix` занято другим проектом).

```bash
pip install helix-agent
pip install "helix-agent[telegram,browser]"
pip install "helix-agent[all]"
```

Команда в терминале по-прежнему: **`helix`**.

## Что нужно сделать

### 1. Аккаунт и имя

- Регистрация на [pypi.org](https://pypi.org/account/register/)
- Проверить, что `helix-agent` свободен
- API-токен или Trusted Publishing с GitHub

### 2. Метаданные (уже в репозитории)

- `pyproject.toml` — `name = "helix-agent"`, зависимости, extras, `license-files`
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

```bash
uv sync --group dev
uv build
# тест:
uv publish --publish-url https://test.pypi.org/legacy/ dist/*
# прод:
uv publish dist/*
```

### 5. Документация для пользователей

После публикации обновить [INSTALLATION.md](INSTALLATION.md) и README: `pip install helix-agent`.

## Ограничения

- Только **Python 3.14+**
- Тяжёлые зависимости (ChromaDB, LangGraph)
- Для browser: после pip — `playwright install chromium`

Полная английская версия: [../en/PYPI.md](../en/PYPI.md).