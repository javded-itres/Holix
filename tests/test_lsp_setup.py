"""holix lsp setup selection parsing and install planning."""

from __future__ import annotations

from pathlib import Path

import pytest
from cli.lsp.install import (
    install_spec,
    install_specs,
    parse_selection,
    toolchain_labels,
)
from core.tools.lsp_servers import CATALOG, LspServerSpec, extra_bin_dirs


def test_parse_recommended_default() -> None:
    specs = parse_selection("", CATALOG)
    assert specs
    assert all(s.recommended for s in specs)
    assert any(s.id == "python-pyright" for s in specs)
    assert any(s.id == "typescript" for s in specs)
    assert all(s.id != "go" for s in specs)


def test_parse_all_and_optional() -> None:
    all_specs = parse_selection("all", CATALOG)
    assert {s.id for s in all_specs} == {s.id for s in CATALOG}
    optional = parse_selection("optional", CATALOG)
    assert optional
    assert all(not s.recommended for s in optional)
    assert any(s.id == "go" for s in optional)


def test_parse_ids_and_numbers() -> None:
    specs = parse_selection("go, rust", CATALOG)
    assert {s.id for s in specs} == {"go", "rust"}
    first = CATALOG[0]
    by_num = parse_selection("1", CATALOG)
    assert by_num == [first]


def test_parse_whitespace_and_aliases() -> None:
    specs = parse_selection("python js go", CATALOG)
    assert {s.id for s in specs} == {"python-pyright", "typescript", "go"}
    cpp = parse_selection("c++", CATALOG)
    assert [s.id for s in cpp] == ["clangd"]
    vue = parse_selection("vue", CATALOG)
    assert [s.id for s in vue] == ["vue"]


def test_parse_mixed_recommended_plus_optional() -> None:
    specs = parse_selection("recommended,go,rust", CATALOG)
    ids = {s.id for s in specs}
    assert "python-pyright" in ids
    assert "typescript" in ids
    assert "go" in ids
    assert "rust" in ids
    assert "python-jedi" not in ids


def test_parse_unknown_raises() -> None:
    with pytest.raises(ValueError, match="unknown"):
        parse_selection("not-a-server", CATALOG)


def test_parse_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("cli.lsp.install.spec_ready", lambda spec: spec.id != "go")
    specs = parse_selection("missing", CATALOG)
    assert [s.id for s in specs] == ["go"]


def test_extra_bin_dirs_include_common_prefixes() -> None:
    texts = [Path(p).as_posix() for p in extra_bin_dirs()]
    assert any(p.endswith("go/bin") or "/go/bin" in p for p in texts)
    assert any(".cargo/bin" in p for p in texts)
    assert any(".npm-global/bin" in p for p in texts)


def test_toolchain_labels_for_go_and_npm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("cli.lsp.install.spec_ready", lambda spec: False)
    go = next(s for s in CATALOG if s.id == "go")
    ts = next(s for s in CATALOG if s.id == "typescript")
    labels = toolchain_labels([go, ts])
    assert any("Go" in item for item in labels)
    assert any("Node.js" in item for item in labels)


def test_install_spec_already_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = next(s for s in CATALOG if s.id == "go")
    monkeypatch.setattr("cli.lsp.install.spec_ready", lambda s: True)
    lines = install_spec(spec)
    assert lines == ["ok: Go already installed"]


def test_install_spec_tries_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = LspServerSpec(
        id="t",
        title="T",
        suffixes=(".t",),
        language_ids=("t",),
        argv=("t-ls",),
        install=(("npm", "t-ls"), ("brew", "t-ls")),
    )
    calls: list[tuple[str, str]] = []

    def fake_try(kind: str, value: str, on_progress=None) -> tuple[bool, str]:
        calls.append((kind, value))
        return False, f"no-{kind}"

    monkeypatch.setattr("cli.lsp.install._try_kind", fake_try)
    monkeypatch.setattr("cli.lsp.install.spec_ready", lambda s: False)
    lines = install_spec(spec)
    assert calls == [("npm", "t-ls"), ("brew", "t-ls")]
    assert any(line.startswith("error:") for line in lines)


def test_install_spec_skips_extra_kind(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = next(s for s in CATALOG if s.id == "python-pyright")
    calls: list[str] = []

    def fake_try(kind: str, value: str, on_progress=None) -> tuple[bool, str]:
        calls.append(kind)
        return False, "no"

    monkeypatch.setattr("cli.lsp.install._try_kind", fake_try)
    monkeypatch.setattr("cli.lsp.install.spec_ready", lambda s: False)
    install_spec(spec)
    assert "extra" not in calls
    assert "pip" in calls
    assert "npm" in calls


def test_install_specs_does_not_batch_pyright_npm(monkeypatch: pytest.MonkeyPatch) -> None:
    py = next(s for s in CATALOG if s.id == "python-pyright")
    ts = next(s for s in CATALOG if s.id == "typescript")
    captured: list[list[str]] = []

    def fake_npm(packages: list[str], on_progress=None) -> tuple[bool, str]:
        captured.append(list(packages))
        return True, "ok"

    monkeypatch.setattr("cli.lsp.install._npm_install", fake_npm)
    monkeypatch.setattr("cli.lsp.install.spec_ready", lambda s: False)
    monkeypatch.setattr(
        "cli.lsp.install.install_spec",
        lambda spec, on_progress=None: [f"ok: {spec.id}"],
    )
    install_specs([py, ts])
    assert captured
    assert "pyright" not in captured[0]
    assert "typescript-language-server" in captured[0]


def test_install_specs_batches_npm(monkeypatch: pytest.MonkeyPatch) -> None:
    ts = next(s for s in CATALOG if s.id == "typescript")
    yaml = next(s for s in CATALOG if s.id == "yaml")
    captured: list[list[str]] = []

    def fake_npm(packages: list[str], on_progress=None) -> tuple[bool, str]:
        captured.append(list(packages))
        return True, "ok"

    monkeypatch.setattr("cli.lsp.install._npm_install", fake_npm)
    monkeypatch.setattr("cli.lsp.install.spec_ready", lambda s: False)
    monkeypatch.setattr(
        "cli.lsp.install.install_spec",
        lambda spec, on_progress=None: [f"ok: {spec.id}"],
    )
    lines = install_specs([ts, yaml])
    assert captured
    pkgs = captured[0]
    assert "typescript-language-server" in pkgs
    assert "yaml-language-server" in pkgs
    assert any("ok:" in line for line in lines)
