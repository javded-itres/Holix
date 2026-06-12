#!/usr/bin/env python3
"""One-shot Helix → Holix rebrand across text sources (run from repo root)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    "node_modules",
}

SKIP_FILES = {
    "uv.lock",
    "search-vectors.npz",
    "rename_to_holix.py",
}

TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".toml",
    ".yml",
    ".yaml",
    ".json",
    ".sh",
    ".ps1",
    ".html",
    ".css",
    ".js",
    ".svg",
    ".txt",
    ".service",
    ".example",
    ".xml",
    ".ini",
    ".cfg",
    ".env",
    ".example",
}

SPECIAL_NAMES = {"Dockerfile", "LICENSE", "CONTRIBUTING.md", ".env.example"}

# Order matters: longer / more specific tokens first.
REPLACEMENTS: list[tuple[str, str]] = [
    ("HelixAgentAi", "HolixAgentAi"),
    ("javded-itres/HelixAgent", "javded-itres/Holix"),
    ("github.com/javded-itres/Helix", "github.com/javded-itres/Holix"),
    ("helix-agent.ru", "holix-agent.ru"),
    ("@helix_agent", "@holix_agent"),
    ("HELIX_NO_VERSION_BUMP", "HOLIX_NO_VERSION_BUMP"),
    ("HELIX_", "HOLIX_"),
    ("HelixRuntimeConfig", "HolixRuntimeConfig"),
    ("resolve_helix_home", "resolve_holix_home"),
    ("helix_home_display", "holix_home_display"),
    ("init_helix_home", "init_holix_home"),
    ("helix_env_path", "holix_env_path"),
    ("helix_home", "holix_home"),
    ("helix_md", "holix_md"),
    ("run_helix", "run_holix"),
    ("helix_deps", "holix_deps"),
    ("helix_react", "holix_react"),
    ("helix_plan_execute", "holix_plan_execute"),
    ("helix-cron", "holix-cron"),
    ("helix-gateway@", "holix-gateway@"),
    ("helix-gateway", "holix-gateway"),
    ("helix.conf", "holix.conf"),
    ("test_gateway_helix_", "test_gateway_holix_"),
    ("test_helix_", "test_holix_"),
    ("gateway_helix_", "gateway_holix_"),
    ("/api/helix/", "/api/holix/"),
    ("api/helix/", "api/holix/"),
    ("routers/helix_", "routers/holix_"),
    ("schemas/helix", "schemas/holix"),
    ("services/helix_", "services/holix_"),
    ("helix.api_server", "holix.api_server"),
    ("object\": \"helix.", "object\": \"holix."),
    ("helix.run", "holix.run"),
    ("helix-agent", "holix-agent"),
    ("X-Helix-", "X-Holix-"),
    ("x_helix_", "x_holix_"),
    ("x-helix-", "x-holix-"),
    ("~/.helix", "~/.holix"),
    ("/.helix", "/.holix"),
    (".helix/", ".holix/"),
    ('/"Helix"', '/"Holix"'),
    (' / "Helix"', ' / "Holix"'),
    ("/Helix\"", "/Holix\""),
    ("/Helix'", "/Holix'"),
    ("/ Helix", "/ Holix"),
    ("helix_", "holix_"),
    ("Helix", "Holix"),
    ("`helix`", "`holix`"),
    ("uv run helix", "uv run holix"),
    ("uv tool install helix", "uv tool install holix"),
    ("pipx run helix", "pipx run holix"),
    (" npx helix", " npx holix"),
    ("helix install", "holix install"),
    ("helix gateway", "holix gateway"),
    ("helix doctor", "holix doctor"),
    ("helix models", "holix models"),
    ("helix profile", "holix profile"),
    ("helix -p", "holix -p"),
    ("helix cron", "holix cron"),
    ("helix logs", "holix logs"),
    ("helix hub", "holix hub"),
    ("helix mcp", "holix mcp"),
    ("helix tui", "holix tui"),
    ("helix chat", "holix chat"),
    ("helix run", "holix run"),
    ("helix setup", "holix setup"),
    ("helix version", "holix version"),
    ("helix start", "holix start"),
    ("helix stop", "holix stop"),
    ("helix configure", "holix configure"),
    ("helix show", "holix show"),
    ("helix docs", "holix docs"),
    ("helix update", "holix update"),
    ("helix memory", "holix memory"),
    ("helix skills", "holix skills"),
    ("helix search", "holix search"),
    ("helix telegram", "holix telegram"),
    ("helix config", "holix config"),
    ("helix = ", "holix = "),
    ("# helix", "# holix"),
    (" helix ", " holix "),
    (" helix\n", " holix\n"),
    (" helix.", " holix."),
    (" helix,", " holix,"),
    (" helix'", " holix'"),
    ('"helix"', '"holix"'),
    ("'helix'", "'holix'"),
    ("> helix", "> holix"),
    ("| helix", "| holix"),
]

FILE_RENAMES: list[tuple[str, str]] = [
    ("api/routers/helix_config.py", "api/routers/holix_config.py"),
    ("api/routers/helix_global.py", "api/routers/holix_global.py"),
    ("api/routers/helix_mcp.py", "api/routers/holix_mcp.py"),
    ("api/routers/helix_models.py", "api/routers/holix_models.py"),
    ("api/routers/helix_profiles.py", "api/routers/holix_profiles.py"),
    ("api/routers/helix_skills.py", "api/routers/holix_skills.py"),
    ("api/routers/helix_telegram.py", "api/routers/holix_telegram.py"),
    ("api/schemas/helix.py", "api/schemas/holix.py"),
    ("api/services/helix_deps.py", "api/services/holix_deps.py"),
    ("core/project/helix_md.py", "core/project/holix_md.py"),
    ("tests/test_helix_md.py", "tests/test_holix_md.py"),
    ("tests/test_gateway_helix_profiles.py", "tests/test_gateway_holix_profiles.py"),
    ("tests/test_gateway_helix_models.py", "tests/test_gateway_holix_models.py"),
    ("tests/test_gateway_helix_skills.py", "tests/test_gateway_holix_skills.py"),
    ("tests/test_gateway_helix_mcp.py", "tests/test_gateway_holix_mcp.py"),
    ("tests/test_gateway_helix_telegram.py", "tests/test_gateway_holix_telegram.py"),
    ("deploy/systemd/helix-gateway.service", "deploy/systemd/holix-gateway.service"),
    ("deploy/systemd/helix-gateway@.service", "deploy/systemd/holix-gateway@.service"),
    ("deploy/systemd/helix.conf.example", "deploy/systemd/holix.conf.example"),
    ("core/skills/bundled/helix-cron", "core/skills/bundled/holix-cron"),
]


def should_process(path: Path) -> bool:
    if path.name in SKIP_FILES:
        return False
    if path.suffix in TEXT_SUFFIXES or path.name in SPECIAL_NAMES:
        return True
    return False


def transform(content: str) -> str:
    for old, new in REPLACEMENTS:
        content = content.replace(old, new)
    return content


def walk_and_replace() -> int:
    changed = 0
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not should_process(path):
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        updated = transform(original)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed += 1
    return changed


def rename_files() -> None:
    import subprocess

    for old, new in FILE_RENAMES:
        src = ROOT / old
        dst = ROOT / new
        if not src.exists():
            print(f"skip missing: {old}", file=sys.stderr)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "mv", str(src), str(dst)], cwd=ROOT, check=True)


def main() -> None:
    count = walk_and_replace()
    print(f"updated {count} files")
    rename_files()
    print("file renames done")


if __name__ == "__main__":
    main()