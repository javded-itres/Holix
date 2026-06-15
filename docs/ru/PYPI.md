# Публикация на PyPI

Руководство по выпуску пакета **Holix** на [PyPI](https://pypi.org).

> **Опубликовано:** [Holix 0.1.8](https://pypi.org/project/Holix/) — `pipx install Holix`.

## Имя пакета

На PyPI проект публикуется как **`Holix`** (не `holix` — это другой пакет на PyPI).

```bash
pip install Holix
pip install "Holix[telegram,browser]"
pip install "Holix[all]"
```

Команда в терминале по-прежнему: **`holix`**.

## Что нужно сделать

### 1. Аккаунт и имя

- Регистрация на [pypi.org](https://pypi.org/account/register/)
- Проверить, что `Holix` свободен
- API-токен или Trusted Publishing с GitHub

### 2. Метаданные (уже в репозитории)

- `pyproject.toml` — `name = "Holix"`, зависимости, extras, `license-files`
- `config.py` включён в wheel (обязательно для `from config import settings`)
- `[project.scripts]` → `holix`

### 3. Перед каждым релизом

1. Поднять версию в `pyproject.toml` и `cli/__init__.py`
2. `uv build` — без ошибок
3. Проверить установку wheel в чистом venv Python 3.12
4. `uv run pytest -m "not llm"`
5. Обновить `docs/CHANGELOG.md`
6. Тег `v0.1.0`

### 4. Публикация через GitHub Actions (рекомендуется)

Workflow: `.github/workflows/publish-pypi.yml`

**Один раз настроить:**

1. **GitHub** → Settings → Environments → создать `pypi` (и `testpypi` для пробных загрузок).
2. **PyPI** → Publishing → Add trusted publisher:

| Поле | Значение |
|------|----------|
| Project | `Holix` |
| Owner | `javded-itres` |
| Repository | `HolixAgent` |
| Workflow | `publish-pypi.yml` |
| Environment | `pypi` |

Токен в secrets **не нужен** при Trusted Publishing.

**Релиз по тегу:**

```bash
git tag v0.1.3
git push origin v0.1.3
```

Workflow проверит совпадение тега и версии в `pyproject.toml`, соберёт wheel, прогонит smoke install и опубликует на PyPI.

**Вручную:** Actions → Publish to PyPI → Run workflow (можно включить TestPyPI).

### 5. Локальная публикация (альтернатива)

PyPI **не принимает пароль аккаунта** — нужен **API token** (`pypi-...`).

```bash
export UV_PUBLISH_TOKEN='pypi-AgENdXNlcm5hbWU6...'
uv build --no-sources
uv publish dist/*
```

### 6. Документация для пользователей

После публикации обновить [INSTALLATION.md](INSTALLATION.md) и README: `pip install Holix`.

## Ограничения

- Только **Python 3.12+**
- Тяжёлые зависимости (ChromaDB, LangGraph)
- Для browser: после pip — `playwright install chromium`

Полная английская версия: [../en/PYPI.md](../en/PYPI.md).