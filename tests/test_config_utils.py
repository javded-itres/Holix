import os

import pytest

from core.config_utils import resolve_env_refs


def test_resolve_env_refs(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.config_utils import substitute_env_in_string

    monkeypatch.setenv("MY_SECRET", "hidden")
    assert resolve_env_refs("${MY_SECRET}") == "hidden"
    assert resolve_env_refs("${ENV:MY_SECRET}") == "hidden"
    assert substitute_env_in_string("Bearer ${MY_SECRET}!") == "Bearer hidden!"
    assert substitute_env_in_string("Bearer ${MISSING}!") == "Bearer ${MISSING}!"


def test_production_requires_auth() -> None:
    from config import Settings

    s = Settings(helix_env="production", require_auth=False)
    assert s.effective_require_auth is True