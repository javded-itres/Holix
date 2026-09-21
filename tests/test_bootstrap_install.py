"""Tests for curl/bootstrap installer helpers."""

from __future__ import annotations

import httpx
from cli.installer.bootstrap import pypi_package_spec
from cli.installer.bootstrap_i18n import bt
from cli.installer.mikrollm import (
    HUB_AUTO_MODEL,
    INSTALL_SH_URL,
    MikroLLMAdmin,
    apply_mikrollm_auto_model,
    parse_csrf_token,
    parse_new_key,
)


def test_pypi_package_spec_minimal() -> None:
    assert pypi_package_spec(full=False) == "Holix"


def test_pypi_package_spec_full() -> None:
    assert pypi_package_spec(full=True) == "Holix[all]"


def test_parse_csrf_token() -> None:
    html = '<html><meta name="csrf-token" content="abc123"></html>'
    assert parse_csrf_token(html) == "abc123"


def test_parse_new_key() -> None:
    html = '<code class="secret" id="new-key">sk-abcdefghijklmnopqrstuvwxyz</code>'
    assert parse_new_key(html).startswith("sk-")


def test_mikrollm_install_uses_github_script(monkeypatch) -> None:
    from cli.installer import mikrollm as ml

    captured: dict[str, object] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["cwd"] = kwargs.get("cwd")

        class P:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return P()

    monkeypatch.setattr(ml.subprocess, "run", fake_run)
    ok, _log = ml.install_mikrollm_binary()
    assert ok
    assert captured["cwd"] is None
    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert cmd[0] == "sh"
    assert INSTALL_SH_URL in cmd[-1]
    assert "curl -fsSL" in cmd[-1]


def test_apply_mikrollm_auto_model() -> None:
    class Cfg:
        default_provider = "ollama"
        model = "qwen2.5-coder:32b"
        temperature = 0.5
        providers = {
            "mikrollm": {
                "default_model": "llama3.2",
                "available_models": ["llama3.2", "qwen"],
            }
        }
        agent_models = {}

    cfg = Cfg()
    apply_mikrollm_auto_model(cfg)
    assert cfg.default_provider == "mikrollm"
    assert cfg.model == HUB_AUTO_MODEL
    assert cfg.providers["mikrollm"]["default_model"] == "auto"
    assert cfg.providers["mikrollm"]["available_models"][0] == "auto"
    assert cfg.agent_models["main"]["provider"] == "mikrollm"
    assert cfg.agent_models["main"]["model"] == "auto"


def test_bootstrap_i18n_mikrollm_keys() -> None:
    assert "MikroLLM" in bt("mikrollm_title", "en")
    assert "сеть" in bt("mikrollm_title", "ru").lower()
    assert "Установить MikroLLM" in bt("mikrollm_configure", "ru")


def test_mikrollm_admin_create_key_and_hub() -> None:
    csrf_html = '<meta name="csrf-token" content="tok">'
    key_html = '<code class="secret" id="new-key">sk-testkeyvalue0123456789</code>'
    state = {"hub": False, "key": False}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/admin/login" and request.method == "POST":
            return httpx.Response(302, headers={"location": "/admin", "set-cookie": "sid=1"})
        if path == "/admin" and request.method == "GET":
            return httpx.Response(200, text=csrf_html)
        if path == "/admin/keys" and request.method == "POST":
            state["key"] = True
            return httpx.Response(200, text=key_html)
        if path == "/admin/hub" and request.method == "POST":
            state["hub"] = True
            return httpx.Response(200, text="ok")
        return httpx.Response(404, text=path)

    transport = httpx.MockTransport(handler)
    admin = MikroLLMAdmin()
    admin.client = httpx.Client(transport=transport, follow_redirects=True)
    admin.login("secret")
    key = admin.create_key(name="holix")
    admin.enable_hub(name="test-node")
    admin.close()
    assert key == "sk-testkeyvalue0123456789"
    assert state["key"] and state["hub"]
