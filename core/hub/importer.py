"""Install skills from ClawHub, git, URLs, Claude marketplaces, and local bundles."""

from __future__ import annotations

import re
import shutil
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.hub.claude_marketplace import ensure_marketplace_repo, materialize_plugin
from core.hub.clawhub import ClawHubClient
from core.hub.hermes_hub import HERMES_GIT_URL, hermes_skill_subpath
from core.hub.lockfile import HubEntry, HubLockfile
from core.hub.normalize import discover_skill_files, parse_skill_file, write_flat_skill
from core.hub.slash_registry import rebuild_slash_registry
from core.hub.sources import git_ref_from_spec, parse_install_source, skills_sh_to_git_url
from core.mcp.installer import clone_or_update_git


@dataclass
class InstallResult:
    skill_name: str
    source: str
    slug: str
    version: str | None
    bundle_dir: Path
    flat_file: Path | None
    entry_id: str
    install_spec: str = ""
    skill_names: list[str] = field(default_factory=list)
    mcp_servers: dict[str, dict[str, Any]] = field(default_factory=dict)


class SkillImporter:
    HUB_SUBDIR = "_hub"

    def __init__(self, skills_dir: Path, lock_path: Path | None = None) -> None:
        self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.hub_root = self.skills_dir / self.HUB_SUBDIR
        self.hub_root.mkdir(parents=True, exist_ok=True)
        lock = lock_path or (self.skills_dir.parent / "hub-lock.json")
        self.lock = HubLockfile(lock)

    def install(
        self,
        spec: str,
        *,
        as_name: str | None = None,
        flat: bool = True,
    ) -> InstallResult:
        parsed = parse_install_source(spec, as_name=as_name)
        install_spec = spec.strip()

        if parsed.kind == "clawhub":
            return self._install_clawhub(
                parsed.ref,
                version=parsed.version,
                as_name=parsed.as_name,
                flat=flat,
                install_spec=install_spec,
            )
        if parsed.kind == "claude":
            mp = "claude-official"
            if "@" in install_spec:
                mp = install_spec.rsplit("@", 1)[-1]
            return self._install_claude_plugin(
                parsed.ref,
                marketplace=mp,
                flat=flat,
                install_spec=install_spec,
            )
        if parsed.kind == "hermes":
            return self._install_git(
                HERMES_GIT_URL,
                subpath=hermes_skill_subpath(parsed.ref),
                as_name=parsed.as_name or parsed.ref,
                source_label=parsed.ref,
                source="hermes",
                slug_hint=parsed.ref,
                flat=flat,
                install_spec=install_spec,
            )
        if parsed.kind == "skills-sh":
            url, sub = skills_sh_to_git_url(parsed.ref)
            return self._install_git(
                url,
                subpath=sub,
                as_name=parsed.as_name,
                source_label=parsed.ref,
                flat=flat,
                install_spec=install_spec,
            )
        if parsed.kind == "git":
            url, ref = git_ref_from_spec(parsed.ref)
            return self._install_git(
                url,
                ref=ref,
                as_name=parsed.as_name,
                source_label=parsed.ref,
                flat=flat,
                install_spec=install_spec,
            )
        if parsed.kind == "url":
            return self._install_url(parsed.ref, as_name=parsed.as_name, flat=flat, install_spec=install_spec)
        if parsed.kind == "path":
            return self._install_path(
                Path(parsed.ref).expanduser(),
                as_name=parsed.as_name,
                source_label=parsed.ref,
                flat=flat,
                install_spec=install_spec,
            )
        raise ValueError(f"Unsupported source kind: {parsed.kind}")

    def remove(self, entry_id: str, *, drop_flat: bool = True) -> list[str]:
        """Remove a hub lock entry, its bundle, and optional flat skill files."""
        entry = self.lock.get(entry_id)
        if not entry:
            raise KeyError(f"Unknown hub entry: {entry_id}")

        removed_names: list[str] = []
        bundle = Path(entry.install_path)
        if bundle.exists():
            for sf in discover_skill_files(bundle):
                parsed = parse_skill_file(sf)
                if parsed and parsed.get("name"):
                    removed_names.append(parsed["name"])
            shutil.rmtree(bundle, ignore_errors=True)

        if drop_flat:
            for name in {entry.skill_name, *removed_names}:
                flat = self.skills_dir / f"{name}.md"
                if flat.exists():
                    flat.unlink()

        self.lock.remove(entry_id)
        rebuild_slash_registry(self.skills_dir)
        return sorted(set(removed_names or [entry.skill_name]))

    def update_all(self) -> list[tuple[str, InstallResult | Exception]]:
        outcomes: list[tuple[str, InstallResult | Exception]] = []
        for entry in self.lock.list_entries():
            spec = entry.install_spec or self._entry_to_spec(entry)
            if not spec:
                outcomes.append((entry.id, ValueError("no install_spec")))
                continue
            try:
                outcomes.append((entry.id, self.install(spec)))
            except Exception as e:
                outcomes.append((entry.id, e))
        rebuild_slash_registry(self.skills_dir)
        return outcomes

    def _entry_to_spec(self, entry: HubEntry) -> str | None:
        if entry.source == "clawhub":
            base = f"clawhub:{entry.slug}"
            return f"{base}@{entry.version}" if entry.version else base
        if entry.source == "claude":
            mp = entry.marketplace or "claude-official"
            return f"claude:{entry.slug}@{mp}"
        if entry.source == "hermes":
            return f"hermes:{entry.slug}"
        if entry.source in ("git", "skills-sh", "url", "path"):
            return entry.slug if entry.slug.startswith(("http", "skills-sh", "/", "~", ".")) else entry.install_path
        return None

    def _install_claude_plugin(
        self,
        plugin_name: str,
        *,
        marketplace: str,
        flat: bool,
        install_spec: str,
    ) -> InstallResult:
        repo_root, data = ensure_marketplace_repo(marketplace)
        plugin_meta = None
        for p in data.get("plugins", []):
            if isinstance(p, dict) and p.get("name") == plugin_name:
                from core.hub.claude_marketplace import MarketplacePlugin

                plugin_meta = MarketplacePlugin(
                    name=p["name"],
                    description=p.get("description") or "",
                    category=p.get("category") or "",
                    homepage=p.get("homepage") or "",
                    source=p.get("source"),
                )
                break
        if not plugin_meta:
            raise ValueError(f"Plugin '{plugin_name}' not in marketplace '{marketplace}'")

        dest = self.hub_root / "claude" / plugin_name
        bundle = materialize_plugin(repo_root, plugin_meta, dest)

        skill_names: list[str] = []
        if flat:
            for skill_file in discover_skill_files(dest):
                parsed = parse_skill_file(skill_file)
                if not parsed:
                    continue
                write_flat_skill(self.skills_dir / f"{parsed['name']}.md", parsed)
                skill_names.append(parsed["name"])

        entry_id = f"claude:{marketplace}:{plugin_name}"
        primary = skill_names[0] if skill_names else plugin_name
        self.lock.upsert(
            HubEntry(
                id=entry_id,
                source="claude",
                slug=plugin_name,
                version=None,
                install_path=str(dest),
                skill_name=primary,
                installed_at=HubLockfile.now_iso(),
                install_spec=install_spec,
                marketplace=marketplace,
            )
        )
        rebuild_slash_registry(self.skills_dir)
        return InstallResult(
            skill_name=primary,
            source="claude",
            slug=plugin_name,
            version=None,
            bundle_dir=dest,
            flat_file=None,
            entry_id=entry_id,
            install_spec=install_spec,
            skill_names=skill_names,
            mcp_servers=bundle.mcp_servers,
        )

    def _install_clawhub(
        self,
        slug: str,
        *,
        version: str | None,
        as_name: str | None,
        flat: bool,
        install_spec: str,
    ) -> InstallResult:
        client = ClawHubClient()
        ver, files = client.fetch_skill_bundle(slug, version)
        bundle_dir = self.hub_root / slug
        if bundle_dir.exists():
            shutil.rmtree(bundle_dir)
        bundle_dir.mkdir(parents=True)
        for rel, content in files.items():
            dest = bundle_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")

        skill_md = bundle_dir / "SKILL.md"
        if not skill_md.exists():
            raise ValueError(f"ClawHub skill '{slug}' has no SKILL.md")
        skill = parse_skill_file(skill_md)
        if not skill:
            raise ValueError(f"Failed to parse SKILL.md for '{slug}'")
        if as_name:
            skill["name"] = re.sub(r"[^a-z0-9-]+", "-", as_name.lower()).strip("-")
        name = skill["name"]
        flat_file = write_flat_skill(self.skills_dir / f"{name}.md", skill) if flat else None

        entry_id = f"clawhub:{slug}"
        self.lock.upsert(
            HubEntry(
                id=entry_id,
                source="clawhub",
                slug=slug,
                version=ver,
                install_path=str(bundle_dir),
                skill_name=name,
                installed_at=HubLockfile.now_iso(),
                install_spec=install_spec,
            )
        )
        rebuild_slash_registry(self.skills_dir)
        return InstallResult(
            name,
            "clawhub",
            slug,
            ver,
            bundle_dir,
            flat_file,
            entry_id,
            install_spec=install_spec,
            skill_names=[name],
        )

    def _install_git(
        self,
        url: str,
        *,
        ref: str | None = None,
        subpath: str | None = None,
        as_name: str | None = None,
        source_label: str | None = None,
        source: str = "git",
        slug_hint: str | None = None,
        flat: bool = True,
        install_spec: str = "",
    ) -> InstallResult:
        folder = _safe_dir_name(url)
        cloned = clone_or_update_git(url, folder)
        if ref:
            from core.mcp.installer import _run

            _run(["git", "-C", str(cloned), "checkout", ref], check=False)

        src = cloned
        if subpath:
            src = cloned / subpath
        return self._install_path(
            src,
            as_name=as_name,
            source=source,
            source_label=source_label or url,
            flat=flat,
            slug_hint=slug_hint or folder,
            install_spec=install_spec or source_label or url,
        )

    def _install_url(
        self,
        url: str,
        *,
        as_name: str | None,
        flat: bool,
        install_spec: str,
    ) -> InstallResult:
        req = urllib.request.Request(url, headers={"User-Agent": "Holix/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
        slug = as_name or _safe_dir_name(url)
        bundle_dir = self.hub_root / slug
        bundle_dir.mkdir(parents=True, exist_ok=True)
        skill_md = bundle_dir / "SKILL.md"
        skill_md.write_text(text, encoding="utf-8")
        return self._finalize_bundle(
            bundle_dir,
            source="url",
            slug=slug,
            version=None,
            as_name=as_name,
            flat=flat,
            entry_id=f"url:{slug}",
            install_spec=install_spec,
        )

    def _install_path(
        self,
        src: Path,
        *,
        as_name: str | None,
        source: str = "path",
        source_label: str,
        flat: bool,
        slug_hint: str | None = None,
        install_spec: str = "",
    ) -> InstallResult:
        src = src.resolve()
        if not src.exists():
            raise FileNotFoundError(src)

        if src.is_file() and src.name.endswith(".md"):
            slug = slug_hint or src.stem
            bundle_dir = self.hub_root / slug
            bundle_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, bundle_dir / "SKILL.md")
            return self._finalize_bundle(
                bundle_dir,
                source=source,
                slug=slug,
                version=None,
                as_name=as_name,
                flat=flat,
                entry_id=f"{source}:{slug}",
                install_spec=install_spec or source_label,
            )

        if (src / "SKILL.md").exists():
            slug = slug_hint or src.name
            bundle_dir = self.hub_root / slug
            if bundle_dir.exists():
                shutil.rmtree(bundle_dir)
            shutil.copytree(src, bundle_dir)
            return self._finalize_bundle(
                bundle_dir,
                source=source,
                slug=slug,
                version=None,
                as_name=as_name,
                flat=flat,
                entry_id=f"{source}:{slug}",
                install_spec=install_spec or source_label,
            )

        # Directory with nested SKILL.md files (e.g. cloned agent-skills repo)
        skill_files = discover_skill_files(src)
        if skill_files:
            slug = slug_hint or src.name
            bundle_dir = self.hub_root / slug
            if bundle_dir.exists():
                shutil.rmtree(bundle_dir)
            shutil.copytree(src, bundle_dir)
            names: list[str] = []
            if flat:
                for sf in discover_skill_files(bundle_dir):
                    parsed = parse_skill_file(sf)
                    if parsed:
                        if as_name and len(skill_files) == 1:
                            parsed["name"] = re.sub(r"[^a-z0-9-]+", "-", as_name.lower()).strip("-")
                        write_flat_skill(self.skills_dir / f"{parsed['name']}.md", parsed)
                        names.append(parsed["name"])
            entry_id = f"{source}:{slug}"
            primary = names[0] if names else slug
            self.lock.upsert(
                HubEntry(
                    id=entry_id,
                    source=source,
                    slug=install_spec or source_label,
                    version=None,
                    install_path=str(bundle_dir),
                    skill_name=primary,
                    installed_at=HubLockfile.now_iso(),
                    install_spec=install_spec or source_label,
                )
            )
            rebuild_slash_registry(self.skills_dir)
            return InstallResult(
                primary,
                source,
                slug,
                None,
                bundle_dir,
                None,
                entry_id,
                install_spec=install_spec or source_label,
                skill_names=names,
            )

        raise ValueError(f"No SKILL.md found at {src}")

    def _finalize_bundle(
        self,
        bundle_dir: Path,
        *,
        source: str,
        slug: str,
        version: str | None,
        as_name: str | None,
        flat: bool,
        entry_id: str,
        install_spec: str,
    ) -> InstallResult:
        skill_md = bundle_dir / "SKILL.md"
        skill = parse_skill_file(skill_md)
        if not skill:
            raise ValueError(f"Invalid SKILL.md in {bundle_dir}")
        if as_name:
            skill["name"] = re.sub(r"[^a-z0-9-]+", "-", as_name.lower()).strip("-")
        name = skill["name"]
        flat_file = write_flat_skill(self.skills_dir / f"{name}.md", skill) if flat else None
        self.lock.upsert(
            HubEntry(
                id=entry_id,
                source=source,
                slug=slug,
                version=version,
                install_path=str(bundle_dir),
                skill_name=name,
                installed_at=HubLockfile.now_iso(),
                install_spec=install_spec,
            )
        )
        rebuild_slash_registry(self.skills_dir)
        return InstallResult(
            name,
            source,
            slug,
            version,
            bundle_dir,
            flat_file,
            entry_id,
            install_spec=install_spec,
            skill_names=[name],
        )


def _safe_dir_name(value: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-")
    return (s[:80] or "skill")