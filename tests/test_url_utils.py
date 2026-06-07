"""Tests for URL hostname helpers."""

from core.hub.sources import parse_install_source
from core.models.catalog import detect_preset_from_url
from core.url_utils import host_is, spec_looks_like_github, url_hostname


def test_host_is_rejects_substring_false_positive():
    assert not host_is("evil-api.openai.com.attacker.tld", "api.openai.com")


def test_host_is_accepts_exact_and_subdomain():
    assert host_is("api.openai.com", "api.openai.com")
    assert host_is("gateway.api.openai.com", "api.openai.com")


def test_spec_looks_like_github():
    assert spec_looks_like_github("https://github.com/org/repo.git")
    assert spec_looks_like_github("git@github.com:org/repo.git")
    assert not spec_looks_like_github("https://evil-github.com.attacker/repo.git")


def test_parse_install_source_github_url():
    parsed = parse_install_source("https://github.com/org/repo")
    assert parsed.kind == "git"


def test_detect_preset_from_url_openai():
    assert detect_preset_from_url("https://api.openai.com/v1") == "openai"
    assert detect_preset_from_url("https://evil-api.openai.com.attacker/v1") is None


def test_detect_preset_from_url_local_ports():
    assert detect_preset_from_url("http://127.0.0.1:11434") == "ollama"
    assert detect_preset_from_url("http://localhost:4000/v1") == "litellm"


def test_url_hostname_git_scp_style():
    assert url_hostname("git@github.com:owner/repo.git") == "github.com"