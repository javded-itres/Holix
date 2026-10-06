"""Optional System One decisions and text-similarity embeddings."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
from core.decision.config import (
    configure_decision,
    configure_embeddings,
    profile_env_secret,
    resolve_decision,
    resolve_embeddings,
    systemone_url,
)
from core.decision.embeddings import cosine, embed_texts
from core.decision.runtime import bind_optional_tools
from core.decision.skills import (
    DECISION_SKILL,
    EMBEDDINGS_SKILL,
    SkillSwitchError,
    apply_skill_switch,
)
from core.decision.systemone import call_systemone, validate_request
from core.skills.bundled import ensure_bundled_assigned_to_main, seed_bundled_skills
from core.tools.systemone import SystemOneDecideTool


def _jev():
    return resolve_decision({"enabled": True, "preset": "jev"}, api_key="test-key")


def test_jev_preset_is_multilingual_default():
    resolved = resolve_decision({"enabled": True, "preset": "jev"})
    assert resolved.model == "jev-latest"
    assert resolved.base_url == "https://api.typesafe.ai"
    assert systemone_url(resolved.base_url) == "https://api.typesafe.ai/v1/systemone"
    assert resolve_decision({}).enabled is False
    assert resolve_decision(None).enabled is False


def test_profile_env_secret_prefers_profile_file(monkeypatch):
    monkeypatch.setattr(
        "core.env_loader.read_profile_env_map",
        lambda profile: {"DECISION_API_KEY": f"file-{profile}"},
    )
    monkeypatch.setenv("DECISION_API_KEY", "from-process")
    assert profile_env_secret("pavel", "DECISION_API_KEY") == "file-pavel"
    assert profile_env_secret("", "DECISION_API_KEY") == "from-process"


def test_nimble_and_api_v1_paths():
    resolved = resolve_decision({"enabled": True, "preset": "nimble"})
    assert resolved.model == "nimble"
    assert systemone_url(resolved.base_url) == "http://127.0.0.1:11434/v1/systemone"
    assert systemone_url("https://example.test/api/v1") == "https://example.test/api/v1/systemone"


def test_same_preset_keeps_pinned_model_switch_replaces_it():
    pinned = configure_decision(configure_decision({}, "jev"), "jev", model="jev-1.13.0")
    assert pinned["model"] == "jev-1.13.0"
    again = configure_decision(pinned, "jev")
    assert again["model"] == "jev-1.13.0"
    local = configure_decision(again, "nimble")
    assert local["model"] == "nimble"
    assert local["base_url"] == "http://127.0.0.1:11434"
    custom = configure_decision({}, "custom", base_url="https://api.typesafe.ai")
    assert custom["model"] == "jev-latest"


def test_invalid_questions_do_not_call_http():
    called = {"n": 0}

    async def post(url, payload, headers, timeout):
        del url, payload, headers, timeout
        called["n"] += 1
        return 200, b"{}"

    resolved = _jev()
    cases = [
        ("", {"q": {"type": "noul", "instructions": "да"}}),
        ("текст", {}),
        ("текст", {"q": {"type": "choice", "criteria": ["a", "b"]}}),
        ("текст", {"q": {"type": "score", "criteria": ["только один"]}}),
        ("текст", {"q": {"type": "noul"}}),
    ]
    for state, questions in cases:
        text = asyncio.run(call_systemone(resolved, state, questions, post=post))
        assert text.startswith("System One error:")
    assert called["n"] == 0


def test_state_language_is_not_rewritten_and_noul_parses():
    seen = {}

    async def post(url, payload, headers, timeout):
        del timeout
        seen["url"] = url
        seen["payload"] = payload
        seen["auth"] = headers.get("Authorization")
        return 200, json.dumps({"probe": {"noul": 0.25}}).encode()

    text = asyncio.run(
        call_systemone(
            _jev(),
            "Привет",
            {"q": {"type": "noul", "instructions": "Это приветствие"}},
            post=post,
        )
    )
    assert seen["payload"]["state"] == "Привет"
    assert seen["payload"]["questions"]["q"]["instructions"] == "Это приветствие"
    assert seen["payload"]["model"] == "jev-latest"
    assert seen["url"] == "https://api.typesafe.ai/v1/systemone"
    assert seen["auth"] == "Bearer test-key"
    assert json.loads(text)["probe"]["noul"] == 0.25


def test_nimble_omits_authorization():
    seen = {}

    async def post(url, payload, headers, timeout):
        del url, payload, timeout
        seen["headers"] = headers
        return 200, b'{"q":{"noul":0.5}}'

    resolved = resolve_decision({"enabled": True, "preset": "nimble"})
    asyncio.run(
        call_systemone(resolved, "текст", {"q": {"type": "noul", "instructions": "да"}}, post=post)
    )
    assert "Authorization" not in seen["headers"]


def test_http_errors_stay_strings():
    resolved = _jev()

    async def unauthorized(url, payload, headers, timeout):
        del url, payload, headers, timeout
        return 401, b'{"error":"no"}'

    async def broken(url, payload, headers, timeout):
        del url, payload, headers, timeout
        raise httpx.ConnectError("secret-body")

    denied = asyncio.run(
        call_systemone(
            resolved, "текст", {"q": {"type": "noul", "instructions": "да"}}, post=unauthorized
        )
    )
    failed = asyncio.run(
        call_systemone(
            resolved, "текст", {"q": {"type": "noul", "instructions": "да"}}, post=broken
        )
    )
    assert "401" in denied
    assert "connection failed" in failed
    assert "secret-body" not in failed


def test_oversized_request_is_not_sent():
    called = {"n": 0}

    async def post(url, payload, headers, timeout):
        del url, payload, headers, timeout
        called["n"] += 1
        return 200, b"{}"

    text = asyncio.run(
        call_systemone(
            _jev(),
            "x" * 2_000_000,
            {"q": {"type": "noul", "instructions": "да"}},
            post=post,
        )
    )
    assert "1 MiB" in text
    assert called["n"] == 0


def test_validate_request_accepts_choice_object():
    assert (
        validate_request("текст", {"q": {"type": "choice", "criteria": {"a": "когда a"}}}) is None
    )


def test_tool_failure_does_not_leak(monkeypatch):
    monkeypatch.setattr("core.tools.execution_context.get_profile_name", lambda: "default")

    class Boom:
        def load_profile(self, name):
            del name
            raise RuntimeError("secret-state")

    monkeypatch.setattr("core.profile.service.ProfileManager", Boom)
    text = asyncio.run(SystemOneDecideTool().execute(state="x", questions={}))
    assert text.startswith("System One error:")
    assert "secret-state" not in text


def test_register_all_respects_the_flag():
    from core.tools.registry import ToolRegistry

    off = ToolRegistry()
    off.register_all()
    assert "systemone_decide" not in off.tools
    assert "text_similarity" not in off.tools

    class Config:
        decision = {"enabled": True, "preset": "nimble"}
        embeddings = {
            "enabled": True,
            "api": "ollama",
            "base_url": "http://127.0.0.1:11434",
            "model": "nomic-embed-text",
        }

    on = ToolRegistry()
    with bind_optional_tools(Config()):
        on.register_all()
    assert "systemone_decide" in on.tools
    assert "text_similarity" in on.tools


def test_opt_in_skills_are_not_seeded(tmp_path: Path):
    dest = tmp_path / "skills"
    seeded = seed_bundled_skills(dest, overwrite=True)
    assert DECISION_SKILL not in seeded
    assert EMBEDDINGS_SKILL not in seeded
    assert not (dest / f"{DECISION_SKILL}.md").exists()
    assert (dest / "holix-studio-frontend-backend.md").is_file()
    assigns, added = ensure_bundled_assigned_to_main({})
    assert DECISION_SKILL not in added
    assert DECISION_SKILL not in assigns.get("main", [])
    assert "holix-studio-frontend-backend" in assigns["main"]


def test_skill_switch_requires_the_block_and_roundtrips(tmp_path: Path):
    try:
        apply_skill_switch(
            {}, block_enabled=False, skills_dir=tmp_path, name=DECISION_SKILL, enabled=True
        )
        raised = False
    except SkillSwitchError:
        raised = True
    assert raised
    assert not (tmp_path / f"{DECISION_SKILL}.md").exists()
    block = apply_skill_switch(
        {"enabled": True, "preset": "nimble"},
        block_enabled=True,
        skills_dir=tmp_path,
        name=DECISION_SKILL,
        enabled=True,
    )
    assert block["skills"][DECISION_SKILL] is True
    assert (tmp_path / f"{DECISION_SKILL}.md").is_file()
    body = (tmp_path / f"{DECISION_SKILL}.md").read_text(encoding="utf-8")
    assert "systemone_decide" in body
    assert "mikrollm" not in body.lower()
    cleared = apply_skill_switch(
        block, block_enabled=True, skills_dir=tmp_path, name=DECISION_SKILL, enabled=False
    )
    assert cleared["skills"][DECISION_SKILL] is False
    assert not (tmp_path / f"{DECISION_SKILL}.md").exists()


def test_embeddings_do_not_replace_memory_embedder():
    source = (Path(__file__).resolve().parents[1] / "core/memory/chroma_embeddings.py").read_text(
        encoding="utf-8"
    )
    assert "core.decision" not in source
    configured = configure_embeddings({}, "ollama", model="nomic-embed-text")
    resolved = resolve_embeddings(configured)
    assert resolved.enabled is True
    assert resolved.api == "ollama"
    assert abs(cosine([1.0, 0.0], [1.0, 0.0]) - 1.0) < 1e-9

    async def post(url, payload, headers, timeout):
        del headers, timeout
        assert url.endswith("/api/embed")
        assert payload["input"] == ["а", "б"]
        return 200, json.dumps({"embeddings": [[1.0, 0.0], [0.0, 1.0]]}).encode()

    vectors = asyncio.run(embed_texts(resolved, ["а", "б"], post=post))
    assert vectors == [[1.0, 0.0], [0.0, 1.0]]


def test_runtime_copies_decision_block():
    from core.di.runtime_config import HolixRuntimeConfig
    from core.profile.service import ProfileConfig

    profile = ProfileConfig(
        profile_name="default",
        decision={"enabled": True, "preset": "nimble"},
        embeddings={"enabled": False},
    )
    runtime = HolixRuntimeConfig.from_profile(profile)
    assert runtime.decision["preset"] == "nimble"
    assert runtime.embeddings == {"enabled": False}
