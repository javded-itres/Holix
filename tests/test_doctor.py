"""Helix doctor checks and helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from cli.core import ProfileConfig, ProfileManager
from cli.doctor.checks import (
    _check_hub_lockfile,
    _check_platform,
    _check_profile_config,
    _check_providers,
)
from cli.doctor.findings import DoctorFinding, Severity
from cli.doctor.fixes import apply_deterministic_fixes
from cli.doctor.llm_doctor import _extract_yaml
from core.hub.lockfile import HubEntry, HubLockfile


def test_extract_yaml_from_fence() -> None:
    raw = "```yaml\nmodel: x\nbase_url: http://localhost\n```"
    assert "model: x" in _extract_yaml(raw)


def test_check_missing_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("cli.doctor.checks.HELIX_HOME", tmp_path)
    monkeypatch.setattr("cli.doctor.checks.PROFILES_DIR", tmp_path / "profiles")
    monkeypatch.setattr("cli.core.HELIX_HOME", tmp_path)
    monkeypatch.setattr("cli.core.PROFILES_DIR", tmp_path / "profiles")

    manager = ProfileManager()
    findings = _check_profile_config("ghost", manager)
    assert any(f.code == "profile.missing" for f in findings)


def test_check_invalid_default_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = ProfileConfig(
        profile_name="t",
        default_provider="missing",
        providers={"ollama": {"base_url": "http://localhost:11434/v1", "default_model": "m"}},
    )
    findings = _check_providers(cfg, "t")
    assert any(f.code == "profile.invalid_default_provider" for f in findings)


def test_fix_create_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("cli.core.HELIX_HOME", tmp_path)
    monkeypatch.setattr("cli.core.PROFILES_DIR", tmp_path / "profiles")

    finding = DoctorFinding(
        code="profile.missing",
        severity=Severity.ERROR.value,
        title="x",
        detail="x",
        recommendation="x",
        fix_id="create_profile",
        context={"profile": "newprof"},
    )
    applied = apply_deterministic_fixes("newprof", [finding])
    assert applied
    assert (tmp_path / "profiles" / "newprof" / "config.yaml").exists()


def test_check_hub_missing_bundle(tmp_path: Path) -> None:
    skills_dir = tmp_path / "data" / "skills"
    skills_dir.mkdir(parents=True)
    lock_path = skills_dir.parent / "hub-lock.json"
    missing = tmp_path / "data" / "skills" / "_hub" / "gone"
    HubLockfile(lock_path).upsert(
        HubEntry(
            id="clawhub:gone@1",
            source="clawhub",
            slug="gone",
            version="1",
            install_path=str(missing),
            skill_name="gone",
            installed_at="2026-01-01T00:00:00+00:00",
        )
    )
    cfg = ProfileConfig(profile_name="t", skills_dir=str(skills_dir))
    findings = _check_hub_lockfile(cfg)
    assert any(f.code == "hub.missing_bundle" for f in findings)


def test_invalid_yaml_finding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("cli.doctor.checks.HELIX_HOME", tmp_path)
    monkeypatch.setattr("cli.doctor.checks.PROFILES_DIR", tmp_path / "profiles")
    monkeypatch.setattr("cli.core.HELIX_HOME", tmp_path)
    monkeypatch.setattr("cli.core.PROFILES_DIR", tmp_path / "profiles")

    manager = ProfileManager()
    profile = "broken"
    manager.create_profile(profile)
    path = manager.get_profile_dir(profile) / "config.yaml"
    path.write_text("model: [invalid yaml", encoding="utf-8")

    findings = _check_profile_config(profile, manager)
    assert any(f.code == "profile.invalid_yaml" for f in findings)


def test_check_platform_info(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("cli.doctor.checks.helix_home_display", lambda: "/tmp/helix-test")
    monkeypatch.setattr("cli.doctor.checks.IS_WINDOWS", False)
    monkeypatch.setattr("cli.doctor.checks.psutil_available", lambda: True)
    monkeypatch.setattr("cli.doctor.checks.clipboard_tools_available", lambda: True)

    findings = _check_platform()
    assert any(f.code == "platform.info" for f in findings)
    assert any("/tmp/helix-test" in f.detail for f in findings)


def test_check_platform_windows_hints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("cli.doctor.checks.helix_home_display", lambda: r"C:\Helix")
    monkeypatch.setattr("cli.doctor.checks.IS_WINDOWS", True)
    monkeypatch.setattr("cli.doctor.checks.process_subagents_supported", lambda: False)
    monkeypatch.setattr("cli.doctor.checks.psutil_available", lambda: False)
    monkeypatch.setattr("cli.doctor.checks.clipboard_tools_available", lambda: True)

    codes = {f.code for f in _check_platform()}
    assert "platform.subagent_process" in codes
    assert "platform.psutil_missing" in codes
    assert "platform.windows_terminal" in codes