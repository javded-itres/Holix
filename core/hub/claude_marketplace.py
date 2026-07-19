"""Claude Code plugin marketplace catalog and install materialization."""

from __future__ import annotations

import io
import json
import logging
import re
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.hub.claude_convert import convert_command_file
from core.hub.claude_mcp import parse_claude_mcp_json
from core.mcp.installer import _run, clone_or_update_git
from core.platform_compat import resolve_holix_home

logger = logging.getLogger(__name__)

HUB_CACHE = resolve_holix_home() / "hub-cache"
USER_AGENT = "Holix/1.0 (+https://github.com/javded-itres/Holix)"

MARKETPLACES: dict[str, dict[str, str]] = {
    "claude-official": {
        "repo": "https://github.com/anthropics/claude-plugins-official.git",
        "marketplace": ".claude-plugin/marketplace.json",
        # Studio browse: fetch JSON without git clone (clone hangs when GitHub is slow).
        "raw_marketplace": (
            "https://raw.githubusercontent.com/anthropics/claude-plugins-official/"
            "main/.claude-plugin/marketplace.json"
        ),
    },
    "claude-code": {
        "repo": "https://github.com/anthropics/claude-code.git",
        "marketplace": "plugins/.claude-plugin/marketplace.json",
        # Repo layout no longer ships marketplace.json; browse uses GitHub contents.
        "github_plugins_api": (
            "https://api.github.com/repos/anthropics/claude-code/contents/plugins"
        ),
    },
}


@dataclass
class MarketplacePlugin:
    name: str
    description: str
    category: str
    homepage: str
    source: Any


@dataclass
class ClaudeInstallBundle:
    plugin_name: str
    marketplace: str
    plugin_dir: Path
    skills_installed: list[str]
    mcp_servers: dict[str, dict[str, Any]]


def _cache_dir_for_repo(url: str) -> Path:
    key = re.sub(r"[^a-zA-Z0-9]+", "-", url).strip("-")[:60]
    return HUB_CACHE / key


_BROWSE_ONLY_MARKER = ".holix-browse-only"


def _legacy_marketplace_repo(repo_url: str) -> Path:
    return resolve_holix_home() / "mcp-servers" / _cache_dir_for_repo(repo_url).name


def _is_git_checkout(path: Path) -> bool:
    return path.is_dir() and (path / ".git").exists()


def _is_incomplete_marketplace_cache(path: Path, marketplace_rel: str) -> bool:
    """True when hub-cache has marketplace.json from browse but no full git tree.

    Catalog browse writes only marketplace.json (and a marker). Install needs
    plugin source dirs (e.g. external_plugins/gitlab) from a real clone.
    """
    if not path.is_dir():
        return False
    if (path / _BROWSE_ONLY_MARKER).is_file():
        return True
    if _is_git_checkout(path):
        return False
    # JSON present but no .git → left by raw/API browse, not a usable checkout
    return (path / marketplace_rel).is_file()


def ensure_marketplace_repo(
    marketplace_id: str,
    *,
    update: bool = False,
) -> tuple[Path, dict[str, Any]]:
    """Resolve marketplace repo under hub-cache.

    Browse/search may use a JSON-only cache (no git). Install must pass
    ``update=True`` (or rely on incomplete-cache detection) so we full-clone
    and materialize plugin paths under the repo.
    """
    if marketplace_id not in MARKETPLACES:
        raise ValueError(
            f"Unknown marketplace '{marketplace_id}'. Known: {', '.join(MARKETPLACES)}"
        )
    meta = MARKETPLACES[marketplace_id]
    dest = _cache_dir_for_repo(meta["repo"])
    mp_rel = meta["marketplace"]
    legacy = _legacy_marketplace_repo(meta["repo"])

    def _read(repo: Path) -> tuple[Path, dict[str, Any]]:
        path = repo / mp_rel
        if not path.is_file():
            raise FileNotFoundError(f"marketplace.json not found: {path}")
        return repo, json.loads(path.read_text(encoding="utf-8"))

    if not update:
        # Prefer real git checkout; JSON-only is enough for catalog list/search.
        if _is_git_checkout(dest) and (dest / mp_rel).is_file():
            return _read(dest)
        if _is_git_checkout(legacy) and (legacy / mp_rel).is_file():
            return _read(legacy)
        if dest.is_dir() and (dest / mp_rel).is_file():
            return _read(dest)
        if legacy.is_dir() and (legacy / mp_rel).is_file():
            return _read(legacy)

    # Install / refresh: never trust browse-only JSON as a plugin source tree
    if dest.is_dir() and (
        _is_incomplete_marketplace_cache(dest, mp_rel) or not _is_git_checkout(dest)
    ):
        logger.info(
            "Replacing incomplete marketplace cache at %s with full git clone",
            dest,
        )
        shutil.rmtree(dest, ignore_errors=True)

    dest.parent.mkdir(parents=True, exist_ok=True)
    if _is_git_checkout(dest) and update:
        try:
            _run(["git", "-C", str(dest), "pull", "--ff-only"], check=False)
        except Exception:
            shutil.rmtree(dest, ignore_errors=True)

    if not dest.is_dir():
        try:
            _run(
                ["git", "clone", "--depth", "1", meta["repo"], str(dest)],
                check=True,
            )
        except Exception:
            # Fall back to legacy mcp-servers layout used by older installs.
            dest = clone_or_update_git(meta["repo"], dest.name)
        marker = dest / _BROWSE_ONLY_MARKER
        if marker.is_file():
            try:
                marker.unlink()
            except OSError:
                pass

    return _read(dest)


_PLUGIN_LIST_CACHE: dict[str, list[MarketplacePlugin]] = {}


def _plugins_from_marketplace_data(data: dict[str, Any]) -> list[MarketplacePlugin]:
    out: list[MarketplacePlugin] = []
    for p in data.get("plugins", []):
        if not isinstance(p, dict) or not p.get("name"):
            continue
        out.append(
            MarketplacePlugin(
                name=p["name"],
                description=(p.get("description") or "")[:300],
                category=p.get("category") or "",
                homepage=p.get("homepage") or "",
                source=p.get("source"),
            )
        )
    out.sort(key=lambda x: x.name.lower())
    return out


def _fetch_raw_marketplace_json(url: str, *, timeout: float = 8.0) -> dict[str, Any] | None:
    """Download marketplace.json over HTTPS (no git). Returns None on failure."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        logger.debug("raw marketplace fetch failed %s: %s", url, exc)
        return None


def _fetch_github_plugin_dirs(api_url: str, *, timeout: float = 8.0) -> dict[str, Any] | None:
    """Build a synthetic marketplace.json from a GitHub contents listing of plugin dirs."""
    try:
        req = urllib.request.Request(
            api_url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            items = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        logger.debug("github plugins list failed %s: %s", api_url, exc)
        return None
    if not isinstance(items, list):
        return None
    plugins: list[dict[str, Any]] = []
    for item in items:
        if item.get("type") != "dir":
            continue
        name = item.get("name") or ""
        if not name or name.startswith("."):
            continue
        plugins.append(
            {
                "name": name,
                "description": f"Claude Code plugin: {name}",
                "category": "claude-code",
                "homepage": item.get("html_url") or "",
                "source": f"./plugins/{name}",
            }
        )
    if not plugins:
        return None
    return {"plugins": plugins}


def _cache_marketplace_json(marketplace_id: str, data: dict[str, Any]) -> None:
    """Best-effort write of marketplace.json under hub-cache for later install/browse.

    Marks the tree as browse-only so install replaces it with a full git clone
    instead of treating JSON-only cache as a complete marketplace checkout.
    """
    meta = MARKETPLACES.get(marketplace_id)
    if not meta:
        return
    try:
        dest = _cache_dir_for_repo(meta["repo"])
        # Never overwrite a real git checkout with JSON-only cache
        if _is_git_checkout(dest):
            return
        path = dest / meta["marketplace"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        (dest / _BROWSE_ONLY_MARKER).write_text("1\n", encoding="utf-8")
    except OSError as exc:
        logger.debug("marketplace cache write failed: %s", exc)


def list_plugins(
    marketplace_id: str,
    *,
    use_cache: bool = True,
    update: bool = False,
    browse_only: bool = False,
) -> list[MarketplacePlugin]:
    if use_cache and not update and marketplace_id in _PLUGIN_LIST_CACHE:
        return _PLUGIN_LIST_CACHE[marketplace_id]

    meta = MARKETPLACES.get(marketplace_id)
    data: dict[str, Any] | None = None

    # Studio catalog browse: never git clone on the request path (keeps admin/IDE alive).
    # Prefer local checkout; else raw.githubusercontent.com JSON (fast, no clone).
    if browse_only and meta and not update:
        dest = _cache_dir_for_repo(meta["repo"])
        legacy = _legacy_marketplace_repo(meta["repo"])
        mp = meta["marketplace"]
        for root in (dest, legacy):
            path = root / mp
            if path.is_file():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    break
                except (OSError, json.JSONDecodeError):
                    data = None
        if data is None:
            raw_url = meta.get("raw_marketplace") or ""
            if raw_url:
                data = _fetch_raw_marketplace_json(raw_url)
            if data is None:
                gh_api = meta.get("github_plugins_api") or ""
                if gh_api:
                    data = _fetch_github_plugin_dirs(gh_api)
            if data:
                _cache_marketplace_json(marketplace_id, data)
        if data is None:
            return []
    else:
        _, data = ensure_marketplace_repo(marketplace_id, update=update)

    out = _plugins_from_marketplace_data(data or {})
    if use_cache:
        _PLUGIN_LIST_CACHE[marketplace_id] = out
    return out


def _plugin_search_score(plugin: MarketplacePlugin, query: str) -> int:
    q = query.lower().strip()
    if not q:
        return 1
    name = plugin.name.lower()
    desc = (plugin.description or "").lower()
    cat = (plugin.category or "").lower()
    if name == q:
        return 1000
    if name.startswith(q):
        return 900 - len(name)
    if q in name:
        return 800 - name.find(q)
    if q in cat:
        return 500
    if q in desc:
        return 300 - min(desc.find(q), 200)
    return 0


def search_plugins(
    marketplace_id: str,
    query: str,
    *,
    limit: int = 15,
    browse_only: bool = False,
) -> list[MarketplacePlugin]:
    all_plugins = list_plugins(marketplace_id, browse_only=browse_only)
    q = (query or "").strip()
    if not q:
        return all_plugins[:limit]

    scored = [( _plugin_search_score(p, q), p) for p in all_plugins]
    scored = [(s, p) for s, p in scored if s > 0]
    scored.sort(key=lambda x: (-x[0], x[1].name.lower()))
    return [p for _, p in scored[:limit]]


def plugin_install_spec(plugin: MarketplacePlugin, marketplace_id: str) -> str:
    return f"claude:{plugin.name}@{marketplace_id}"


def source_needs_marketplace_checkout(source: Any) -> bool:
    """True when plugin lives inside the marketplace monorepo (relative path)."""
    if isinstance(source, str):
        return True
    if isinstance(source, dict):
        kind = str(source.get("source") or "").lower()
        # Remote plugin trees are cloned separately from marketplace.json metadata.
        return kind not in ("url", "github", "git-subdir")
    return True


def _plugin_ref(source: dict[str, Any]) -> str | None:
    for key in ("sha", "commit", "ref", "tag"):
        val = source.get(key)
        if val:
            return str(val)
    return None


_GITHUB_REPO_RE = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com[/:](?P<owner>[^/]+)/(?P<repo>[^/#?\s]+)",
    re.I,
)


def _parse_github_owner_repo(url_or_repo: str) -> tuple[str, str] | None:
    s = (url_or_repo or "").strip()
    if not s:
        return None
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", s):
        owner, repo = s.split("/", 1)
        return owner, repo.removesuffix(".git")
    m = _GITHUB_REPO_RE.search(s)
    if not m:
        return None
    return m.group("owner"), m.group("repo").removesuffix(".git")


def _cache_looks_ready(path: Path) -> bool:
    if not path.is_dir():
        return False
    # Prefer non-empty trees that are not a half-finished git clone
    if (path / ".git").is_dir() and not any(
        p.name != ".git" for p in path.iterdir()
    ):
        return False
    return any(path.iterdir())


def _download_github_archive(owner: str, repo: str, ref: str | None, dest: Path) -> bool:
    """Download GitHub tarball into dest. Prefer this over git (often hangs on slow links)."""
    refs = [r for r in (ref, "main", "master") if r]
    # de-dupe preserve order
    seen: set[str] = set()
    ordered: list[str] = []
    for r in refs:
        if r not in seen:
            seen.add(r)
            ordered.append(r)

    last_err: Exception | None = None
    for pin in ordered:
        for base in (
            f"https://codeload.github.com/{owner}/{repo}/tar.gz/{pin}",
            f"https://github.com/{owner}/{repo}/archive/{pin}.tar.gz",
        ):
            try:
                req = urllib.request.Request(
                    base,
                    headers={"User-Agent": USER_AGENT, "Accept": "application/x-gzip"},
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    payload = resp.read()
                with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as tar:
                    # Archives extract as repo-ref/… — strip top directory
                    members = [m for m in tar.getmembers() if m.name and not m.name.startswith("/")]
                    if not members:
                        continue
                    top = members[0].name.split("/")[0]
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if dest.exists():
                        shutil.rmtree(dest, ignore_errors=True)
                    with tempfile.TemporaryDirectory(prefix="holix-plugin-") as tmp:
                        tmp_path = Path(tmp)
                        tar.extractall(tmp_path)
                        extracted = tmp_path / top
                        if not extracted.is_dir():
                            # flat extract fallback
                            extracted = tmp_path
                        shutil.copytree(extracted, dest)
                if _cache_looks_ready(dest):
                    logger.info("Downloaded plugin archive %s/%s@%s → %s", owner, repo, pin, dest)
                    return True
            except (urllib.error.URLError, TimeoutError, tarfile.TarError, OSError) as exc:
                last_err = exc
                logger.debug("github archive %s failed: %s", base, exc)
                continue
    if last_err:
        logger.warning("github archive download failed for %s/%s: %s", owner, repo, last_err)
    return False


def _fetch_plugin_repo(url: str, ref: str | None = None) -> Path:
    """Materialize a remote plugin repo into hub-cache (archive preferred, git fallback)."""
    dest = _cache_dir_for_repo(url if not ref else f"{url}@{ref}")
    dest_url = _cache_dir_for_repo(url)
    # Reuse complete cache by URL (ignore pin when tree already present)
    for candidate in (dest, dest_url):
        if _cache_looks_ready(candidate):
            return candidate

    gh = _parse_github_owner_repo(url)
    if gh:
        owner, repo = gh
        if _download_github_archive(owner, repo, ref, dest):
            return dest

    # git fallback (may hang on restricted networks — last resort)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_dir():
        shutil.rmtree(dest, ignore_errors=True)
    try:
        _run(["git", "clone", "--depth", "1", url, str(dest)], check=True)
    except Exception:
        dest = clone_or_update_git(url, dest.name)
    if ref:
        _run(["git", "-C", str(dest), "fetch", "--depth", "1", "origin", ref], check=False)
        _run(["git", "-C", str(dest), "checkout", ref], check=False)
    return dest


def resolve_plugin_source(repo_root: Path, source: Any) -> Path:
    if isinstance(source, str):
        rel = source.lstrip("./")
        path = (repo_root / rel).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Plugin path not found: {path}")
        return path

    if isinstance(source, dict):
        kind = str(source.get("source") or "").lower()
        if kind == "git-subdir":
            url = source.get("url")
            sub = source.get("path", "")
            ref = _plugin_ref(source)
            if not url:
                raise ValueError("git-subdir source missing url")
            cloned = _fetch_plugin_repo(str(url), ref)
            dest = (cloned / sub).resolve() if sub else cloned
            if not dest.exists():
                raise FileNotFoundError(dest)
            return dest

        if kind == "url":
            url = source.get("url")
            if not url:
                raise ValueError("url source missing url")
            return _fetch_plugin_repo(str(url), _plugin_ref(source))

        if kind == "github":
            repo = source.get("repo") or source.get("url") or ""
            repo = str(repo).strip()
            if not repo:
                raise ValueError("github source missing repo")
            if repo.startswith("http://") or repo.startswith("https://"):
                url = repo if repo.endswith(".git") else f"{repo.rstrip('/')}.git"
            else:
                owner_repo = repo.removeprefix("github.com/").strip("/")
                url = f"https://github.com/{owner_repo}.git"
            return _fetch_plugin_repo(url, _plugin_ref(source))

    raise ValueError(f"Unsupported plugin source: {source!r}")


def materialize_plugin(
    repo_root: Path,
    plugin: MarketplacePlugin,
    dest_root: Path,
) -> ClaudeInstallBundle:
    src = resolve_plugin_source(repo_root, plugin.source)
    if dest_root.exists():
        shutil.rmtree(dest_root)
    shutil.copytree(src, dest_root, ignore=shutil.ignore_patterns(".git"))

    skills_installed: list[str] = []

    skills_dir = dest_root / "skills"
    if skills_dir.is_dir():
        for skill_md in skills_dir.rglob("SKILL.md"):
            rel = skill_md.relative_to(dest_root)
            skills_installed.append(str(rel.parent or "skills"))

    commands_dir = dest_root / "commands"
    if commands_dir.is_dir():
        out_commands = dest_root / "_holix_commands"
        out_commands.mkdir(exist_ok=True)
        for cmd_file in commands_dir.glob("*.md"):
            skill_name = re.sub(r"[^a-z0-9]+", "-", f"{plugin.name}-{cmd_file.stem}".lower()).strip("-")
            bundle = out_commands / skill_name
            bundle.mkdir(exist_ok=True)
            (bundle / "SKILL.md").write_text(
                convert_command_file(cmd_file, plugin_name=plugin.name),
                encoding="utf-8",
            )
            skills_installed.append(str(bundle.relative_to(dest_root)))

    mcp_servers: dict[str, dict[str, Any]] = {}
    mcp_file = dest_root / ".mcp.json"
    if mcp_file.exists():
        raw = json.loads(mcp_file.read_text(encoding="utf-8"))
        mcp_servers = parse_claude_mcp_json(raw)

    return ClaudeInstallBundle(
        plugin_name=plugin.name,
        marketplace=repo_root.name,
        plugin_dir=dest_root,
        skills_installed=skills_installed,
        mcp_servers=mcp_servers,
    )