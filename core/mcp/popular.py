"""Curated list of popular MCP servers for easy installation via `holix mcp install`."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PopularMCPServer:
    key: str
    display_name: str
    description: str
    transport: str = "stdio"
    command: str = "npx"
    args_template: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    # Interactive params the user must/ can provide (key -> prompt text)
    param_prompts: dict[str, str] = field(default_factory=dict)
    default_params: dict[str, str] = field(default_factory=dict)
    # Category for grouping in UI
    category: str = "general"
    repo_url: str | None = None
    # Notes shown to user (e.g. "Requires GITHUB_TOKEN env var")
    notes: str = ""


# Popular servers (extend as more become standard)
# Verified against official sources (modelcontextprotocol/servers README, subproject READMEs, npm, pypi, vendor repos) as of 2026.
# Many former reference servers were archived to servers-archived; we point to maintained/official successors.
POPULAR_SERVERS: dict[str, PopularMCPServer] = {
    "filesystem": PopularMCPServer(
        key="filesystem",
        display_name="Filesystem (read/write/list)",
        description="Access local files and directories. Restrict to specific paths for safety.",
        command="npx",
        args_template=["-y", "@modelcontextprotocol/server-filesystem", "{allowed_paths}"],
        param_prompts={
            "allowed_paths": "Allowed root directories (space or comma separated, e.g. /Users/you/projects /tmp)"
        },
        default_params={"allowed_paths": "."},
        category="filesystem",
        repo_url="https://github.com/modelcontextprotocol/servers",
        notes="Active reference server (monorepo src/filesystem). npx recommended. Always restrict paths for safety.",
    ),
    "github": PopularMCPServer(
        key="github",
        display_name="GitHub (official)",
        description="Official GitHub MCP: repos, issues, PRs, code, Actions, etc. (Docker-based local server).",
        command="docker",
        args_template=["run", "-i", "--rm", "-e", "GITHUB_PERSONAL_ACCESS_TOKEN", "ghcr.io/github/github-mcp-server"],
        env={"GITHUB_PERSONAL_ACCESS_TOKEN": ""},  # prompted as secret
        category="dev",
        repo_url="https://github.com/github/github-mcp-server",
        notes="Uses GitHub's official Go-based MCP server via Docker (recommended). Requires Docker running + PAT (scopes: repo, read:org, etc.). Alternative remote/http connector available in some hosts.",
    ),
    "context7": PopularMCPServer(
        key="context7",
        display_name="Context7",
        description="Up-to-date documentation, code examples and context for libraries and frameworks (requires free API key from Upstash).",
        command="npx",
        args_template=["-y", "@upstash/context7-mcp"],
        env={"CONTEXT7_API_KEY": ""},
        category="docs",
        repo_url="https://github.com/upstash/context7",
        notes="Correct repo: https://github.com/upstash/context7 . Uses CONTEXT7_API_KEY env (prompted securely during install). Package: @upstash/context7-mcp. Get key at https://context7.com/dashboard (keys start with ctx7sk-). Free tier has rate limits. Alternative: remote https://mcp.context7.com/mcp with header.",
    ),
    "compass": PopularMCPServer(
        key="compass",
        display_name="MCP Compass",
        description="Discover and recommend other MCP servers using natural language queries. Great for finding the right tool for a task.",
        command="npx",
        args_template=["-y", "@liuyoshio/mcp-compass"],
        category="discovery",
        repo_url="https://github.com/liuyoshio/mcp-compass",
        notes="Backend API (registry.mcphub.io) can be flaky and return 5xx errors (e.g. Cloudflare 525). Has a web UI for manual exploration too. Installed as 'compass' / 'mcp-compass'.",
    ),
    "postgres": PopularMCPServer(
        key="postgres",
        display_name="PostgreSQL (Postgres MCP Pro)",
        description="Query/inspect Postgres with extras (health, explain, safe mode). Recommended maintained server.",
        command="uvx",
        args_template=["postgres-mcp"],
        env={"DATABASE_URI": ""},
        category="database",
        repo_url="https://github.com/crystaldba/postgres-mcp",
        notes="Replaces archived reference (which had SQL injection issues). Set DATABASE_URI env to postgresql://... . Add --access-mode=restricted to args for safer execution (edit config after install). Requires 'uv' tool.",
    ),
    "sqlite": PopularMCPServer(
        key="sqlite",
        display_name="SQLite",
        description="Query local SQLite database files (official Python reference style via uvx).",
        command="uvx",
        args_template=["mcp-server-sqlite", "--db-path", "{db_path}"],
        param_prompts={"db_path": "Absolute path to .sqlite / .db file (e.g. /Users/you/app.db or ./project.db)"},
        default_params={"db_path": "./data.db"},
        category="database",
        repo_url="https://github.com/modelcontextprotocol/servers",
        notes="Python reference implementation (archived from monorepo but package mcp-server-sqlite still available via uvx/pip). Use absolute paths preferred.",
    ),
    "brave-search": PopularMCPServer(
        key="brave-search",
        display_name="Brave Search (official)",
        description="Web, local, news, images, video search via Brave Search API (official Brave server).",
        command="npx",
        args_template=["-y", "@brave/brave-search-mcp-server", "--transport", "stdio"],
        env={"BRAVE_API_KEY": ""},
        category="search",
        repo_url="https://github.com/brave/brave-search-mcp-server",
        notes="Replaces archived reference. Get free/pro API key at https://brave.com/search/api/ . Uses --transport stdio (current default).",
    ),
    "fetch": PopularMCPServer(
        key="fetch",
        display_name="Web Fetch",
        description="Fetch and extract content from web pages (HTML->Markdown etc.). Caution: can reach internal IPs.",
        command="uvx",
        args_template=["mcp-server-fetch"],
        category="web",
        repo_url="https://github.com/modelcontextprotocol/servers",
        notes="Active reference (now Python: mcp-server-fetch via uvx). See README for --ignore-robots-txt etc. Security note in upstream.",
    ),
    "git": PopularMCPServer(
        key="git",
        display_name="Git (local repo operations)",
        description="Run git commands, view status, diffs, commit, branches, etc. on local repositories.",
        command="uvx",
        args_template=["mcp-server-git", "--repository", "{repo_path}"],
        param_prompts={"repo_path": "Path to a git repository (absolute or relative, e.g. . or /path/to/repo)"},
        default_params={"repo_path": "."},
        category="dev",
        repo_url="https://github.com/modelcontextprotocol/servers",
        notes="Active reference (Python via uvx mcp-server-git). --repository flag is supported.",
    ),
}

CATEGORIES = sorted({s.category for s in POPULAR_SERVERS.values()})


def get_popular_list() -> list[PopularMCPServer]:
    return list(POPULAR_SERVERS.values())


def get_popular_by_key(key: str) -> PopularMCPServer | None:
    return POPULAR_SERVERS.get(key)
