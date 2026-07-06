"""Detect user messages that need live web research."""

from __future__ import annotations

import re

_REPEAT_SEARCH_RE = re.compile(
    r"(?:повтори|ещё?\s*раз|снова)\s+(?:поиск|search)",
    re.IGNORECASE,
)
_WEB_SEARCH_CALL_RE = re.compile(
    r"web_search\s*\(\s*['\"](.+?)['\"]\s*\)",
    re.IGNORECASE | re.DOTALL,
)
_WEB_SEARCH_TOPIC_RES = (
    re.compile(
        r"найди\s+(?:в\s+)?(?:интернете?|интеренете?|сети|web)\s+"
        r"(?:информацию\s+)?(?:по\s+)?(.+)$",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"поиск(?:ай)?\s+(?:в\s+)?(?:интернете?|интеренете?|сети)?\s*(.+)$",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"search(?:\s+the\s+web|\s+online)?\s+for\s+(.+)$",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"исследуй\s+(?:тему\s+)?(.+)$",
        re.IGNORECASE | re.DOTALL,
    ),
)

_SMALL_TALK_RE = re.compile(
    r"^(?:"
    r"привет|здравствуй|добрый\s+(?:день|утро|вечер)|"
    r"спасибо|благодарю|thanks|thank\s+you|"
    r"ok|ок|да|нет|ага|угу|"
    r"хорошо|понятно|ладно|пока|до\s+свидания|"
    r"ты\s+тут|ты\s+здесь"
    r")\s*[!.?]*$",
    re.IGNORECASE,
)

_LOCAL_TASK_RE = re.compile(
    r"(?:"
    r"^/|"
    r"напиши\s+(?:код|функцию|скрипт|тест|класс)|"
    r"создай\s+(?:файл|скилл|скрипт|проект|ветку|коммит)|"
    r"исправь\s+(?:баг|ошибк|код)|"
    r"отредактируй|refactor|рефактор|"
    r"запусти\s+(?:тест|команд|скрипт|holix)|"
    r"выполни\s+команд|"
    r"git\s+(?:commit|push|pull|merge)|"
    r"сделай\s+(?:commit|pr|pull\s+request)|"
    r"покажи\s+(?:код|файл|diff|лог|статус\s+профил)|"
    r"останови|/stop|"
    r"переключи\s+(?:модель|профиль)|"
    r"установи\s+пакет|pip\s+install|npm\s+install"
    r")",
    re.IGNORECASE,
)

_SEARCH_ACTION_RE = re.compile(
    r"(?:"
    r"найди|найти|поищи|поискать|"
    r"загугли|гугл(?:ь|и)?|"
    r"узнай|выясни|"
    r"проверь|проверить|"
    r"посмотри|глянь|"
    r"собери\s+информацию|"
    r"подбери|"
    r"сравни|"
    r"исследуй|"
    r"search|lookup|look\s+up|find\s+out|google"
    r")\b",
    re.IGNORECASE,
)

_FRESH_DATA_RE = re.compile(
    r"(?:"
    r"сегодня|сейчас|вчера|на\s+данный\s+момент|"
    r"актуальн|последн|свеж|"
    r"новост|"
    r"в\s+интернете?|в\s+сети|online|"
    r"что\s+нового|что\s+случилось"
    r")",
    re.IGNORECASE,
)

_QUESTION_START_RE = re.compile(
    r"(?:^|[,.:;]\s*)(?:"
    r"какой|какая|какие|каково|"
    r"по\s+какой|"
    r"где|куда|откуда|"
    r"когда|"
    r"сколько|"
    r"кто|"
    r"что\s+(?:такое|это|случилось|нового|известно|происходит)|"
    r"почему|зачем|"
    r"есть\s+ли|"
    r"были\s+ли|"
    r"как\s+(?:лучше|обстоят|дела|работает|сейчас|часто)|"
    r"можно\s+ли|"
    r"стоит\s+ли|"
    r"какая\s+ситуация|какая\s+обстановка|"
    r"расскажи\s+(?:про|о|об)|"
    r"дай\s+(?:информацию|справку|обзор)|"
    r"опиши|"
    r"what\s+is|who\s+is|where\s+is|when\s+did|how\s+much|how\s+many"
    r")\b",
    re.IGNORECASE,
)

_CHOICE_COMPARE_RE = re.compile(
    r"(?:"
    r"лучше|хуже|"
    r"сравни|сравнение|"
    r"или\s+лучше|"
    r"что\s+выбрать|"
    r"какой\s+вариант|"
    r"какой\s+маршрут|"
    r"по\s+какой\s+дорог"
    r")",
    re.IGNORECASE,
)

_TOPIC_CONTEXT_RE = re.compile(
    r"(?:"
    r"дорог|маршрут|трасс|ехать|лететь|"
    r"цен[аы]|курс|стоимость|"
    r"погод|температур|"
    r"работает|открыт|закрыт|"
    r"новост|событи|"
    r"компани|продукт|сервис|"
    r"закон|регулирован|"
    r"релиз|верси|"
    r"азс|бензин|топлив|заправк"
    r")",
    re.IGNORECASE,
)

_MIN_LEN = 8


def _clean_query(raw: str) -> str:
    q = (raw or "").strip().strip("«»\"'.")
    q = re.split(r"\s+и\s+пришли", q, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    return q[:500]


def _is_agent_meta_request(text: str) -> bool:
    from core.direct_dispatch.intent import (
        is_status_request,
        is_subagent_list_request,
        is_work_activity_request,
    )

    return (
        is_subagent_list_request(text)
        or is_status_request(text)
        or is_work_activity_request(text)
    )


def extract_search_topic(text: str) -> str | None:
    explicit = _WEB_SEARCH_CALL_RE.search(text)
    if explicit:
        return _clean_query(explicit.group(1))

    stripped = text.strip()
    for pattern in _WEB_SEARCH_TOPIC_RES:
        match = pattern.search(stripped)
        if match:
            q = _clean_query(match.group(1))
            if len(q) >= 3:
                return q
    return None


def is_web_research_request(text: str) -> bool:
    """True when the user needs live web data (delegate to web_researcher).

    Detects general information-seeking and search queries, not only
    fuel/route niche patterns. Local agent tasks and small talk are excluded.
    """
    stripped = (text or "").strip()
    if not stripped or len(stripped) < _MIN_LEN:
        return False

    if stripped.startswith("/"):
        return False

    if _SMALL_TALK_RE.match(stripped):
        return False

    if _is_agent_meta_request(stripped):
        return False

    if _LOCAL_TASK_RE.search(stripped):
        return False

    if _REPEAT_SEARCH_RE.search(stripped):
        return True

    if extract_search_topic(stripped):
        return True

    if _SEARCH_ACTION_RE.search(stripped):
        return True

    if _FRESH_DATA_RE.search(stripped):
        return True

    has_question = "?" in stripped
    has_question_start = bool(_QUESTION_START_RE.search(stripped))

    if has_question_start and (has_question or len(stripped) >= 12):
        return True

    if has_question and len(stripped) >= 12 and _TOPIC_CONTEXT_RE.search(stripped):
        return True

    if _CHOICE_COMPARE_RE.search(stripped) and len(stripped) >= 15:
        return True

    if has_question_start and _TOPIC_CONTEXT_RE.search(stripped):
        return True

    if re.search(r"проблем", stripped, re.IGNORECASE) and _TOPIC_CONTEXT_RE.search(stripped):
        return True

    return False