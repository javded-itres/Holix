"""Language-server catalog, PATH detection, and install hints for the lsp tool."""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class LspServerSpec:
    id: str
    title: str
    suffixes: tuple[str, ...]
    language_ids: tuple[str, ...]
    argv: tuple[str, ...]
    recommended: bool = False
    backend: Literal["lsp", "jedi"] = "lsp"
    install: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class ResolvedLsp:
    spec: LspServerSpec
    argv: list[str]
    language_id: str
    kind: Literal["jedi", "lsp"]


_LANGUAGE_ID_BY_SUFFIX: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescriptreact",
    ".js": "javascript",
    ".jsx": "javascriptreact",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".json": "json",
    ".jsonc": "jsonc",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".sh": "shellscript",
    ".bash": "shellscript",
    ".zsh": "shellscript",
    ".md": "markdown",
    ".markdown": "markdown",
    ".lua": "lua",
    ".php": "php",
    ".rb": "ruby",
    ".vue": "vue",
    ".sql": "sql",
    ".toml": "toml",
    ".dockerfile": "dockerfile",
}

CATALOG: tuple[LspServerSpec, ...] = (
    LspServerSpec(
        id="python-pyright",
        title="Python (Pyright)",
        suffixes=(".py", ".pyi"),
        language_ids=("python", "py"),
        argv=("pyright-langserver", "--stdio"),
        recommended=True,
        install=(
            ("extra", "lsp"),
            ("pip", "pyright"),
            ("npm", "pyright"),
        ),
    ),
    LspServerSpec(
        id="python-basedpyright",
        title="Python (basedpyright)",
        suffixes=(".py", ".pyi"),
        language_ids=("python", "py"),
        argv=("basedpyright-langserver", "--stdio"),
        recommended=False,
        install=(("pip", "basedpyright"),),
    ),
    LspServerSpec(
        id="python-pylsp",
        title="Python (pylsp)",
        suffixes=(".py", ".pyi"),
        language_ids=("python", "py"),
        argv=("pylsp",),
        recommended=False,
        install=(("pip", "python-lsp-server"),),
    ),
    LspServerSpec(
        id="python-jedi",
        title="Python (jedi, fallback)",
        suffixes=(".py", ".pyi"),
        language_ids=("python", "py"),
        argv=(),
        recommended=False,
        backend="jedi",
        install=(("pip", "jedi"),),
    ),
    LspServerSpec(
        id="typescript",
        title="JavaScript / TypeScript",
        suffixes=(".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"),
        language_ids=("typescript", "javascript", "javascriptreact", "typescriptreact"),
        argv=("typescript-language-server", "--stdio"),
        recommended=True,
        install=(("npm", "typescript typescript-language-server"),),
    ),
    LspServerSpec(
        id="json",
        title="JSON",
        suffixes=(".json", ".jsonc"),
        language_ids=("json", "jsonc"),
        argv=("vscode-json-language-server", "--stdio"),
        recommended=True,
        install=(("npm", "vscode-langservers-extracted"),),
    ),
    LspServerSpec(
        id="html",
        title="HTML",
        suffixes=(".html", ".htm"),
        language_ids=("html",),
        argv=("vscode-html-language-server", "--stdio"),
        recommended=True,
        install=(("npm", "vscode-langservers-extracted"),),
    ),
    LspServerSpec(
        id="css",
        title="CSS",
        suffixes=(".css", ".scss", ".less"),
        language_ids=("css", "scss", "less"),
        argv=("vscode-css-language-server", "--stdio"),
        recommended=True,
        install=(("npm", "vscode-langservers-extracted"),),
    ),
    LspServerSpec(
        id="yaml",
        title="YAML",
        suffixes=(".yaml", ".yml"),
        language_ids=("yaml",),
        argv=("yaml-language-server", "--stdio"),
        recommended=True,
        install=(("npm", "yaml-language-server"),),
    ),
    LspServerSpec(
        id="bash",
        title="Bash / shell",
        suffixes=(".sh", ".bash", ".zsh"),
        language_ids=("shellscript", "bash", "sh"),
        argv=("bash-language-server", "start"),
        recommended=True,
        install=(("npm", "bash-language-server"),),
    ),
    LspServerSpec(
        id="dockerfile",
        title="Dockerfile",
        suffixes=(".dockerfile",),
        language_ids=("dockerfile",),
        argv=("docker-langserver", "--stdio"),
        recommended=True,
        install=(("npm", "dockerfile-language-server-nodejs"),),
    ),
    LspServerSpec(
        id="go",
        title="Go",
        suffixes=(".go",),
        language_ids=("go",),
        argv=("gopls",),
        recommended=False,
        install=(
            ("go", "golang.org/x/tools/gopls@latest"),
            ("brew", "gopls"),
        ),
    ),
    LspServerSpec(
        id="rust",
        title="Rust",
        suffixes=(".rs",),
        language_ids=("rust",),
        argv=("rust-analyzer",),
        recommended=False,
        install=(
            ("rustup", "component add rust-analyzer"),
            ("brew", "rust-analyzer"),
        ),
    ),
    LspServerSpec(
        id="clangd",
        title="C / C++",
        suffixes=(".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh"),
        language_ids=("c", "cpp"),
        argv=("clangd",),
        recommended=False,
        install=(
            ("brew", "llvm"),
            ("apt", "clangd"),
        ),
    ),
    LspServerSpec(
        id="lua",
        title="Lua",
        suffixes=(".lua",),
        language_ids=("lua",),
        argv=("lua-language-server",),
        recommended=False,
        install=(("brew", "lua-language-server"),),
    ),
    LspServerSpec(
        id="php",
        title="PHP",
        suffixes=(".php",),
        language_ids=("php",),
        argv=("intelephense", "--stdio"),
        recommended=False,
        install=(("npm", "intelephense"),),
    ),
    LspServerSpec(
        id="ruby",
        title="Ruby",
        suffixes=(".rb",),
        language_ids=("ruby",),
        argv=("solargraph", "stdio"),
        recommended=False,
        install=(("gem", "solargraph"),),
    ),
    LspServerSpec(
        id="vue",
        title="Vue",
        suffixes=(".vue",),
        language_ids=("vue",),
        argv=("vue-language-server", "--stdio"),
        recommended=False,
        install=(("npm", "@vue/language-server"),),
    ),
    LspServerSpec(
        id="markdown",
        title="Markdown",
        suffixes=(".md", ".markdown"),
        language_ids=("markdown",),
        argv=("marksman",),
        recommended=False,
        install=(("brew", "marksman"),),
    ),
    LspServerSpec(
        id="toml",
        title="TOML",
        suffixes=(".toml",),
        language_ids=("toml",),
        argv=("taplo", "lsp", "stdio"),
        recommended=False,
        install=(
            ("cargo", "taplo-cli --features lsp"),
            ("npm", "@taplo/cli"),
        ),
    ),
)


def language_id_for(path: Path, language: str = "") -> str:
    raw = (language or "").strip().lower()
    if raw in {"py", "python"}:
        return "python"
    if raw:
        return raw
    suffix = path.suffix.lower()
    name = path.name.lower()
    if name == "dockerfile" or name.endswith(".dockerfile"):
        return "dockerfile"
    return _LANGUAGE_ID_BY_SUFFIX.get(suffix, suffix.lstrip(".") or "plaintext")


def which_argv(argv: tuple[str, ...] | list[str]) -> list[str] | None:
    """Resolve argv[0] from PATH and the Holix interpreter's bin/ (venv / uv tool)."""
    if not argv:
        return None
    name = argv[0]
    found = shutil.which(name)
    if found:
        return [found, *list(argv[1:])]
    # Do not Path.resolve() — on macOS the venv python is a symlink out of bin/.
    bindir = Path(sys.executable).expanduser().parent
    for extra in (name, f"{name}.exe", f"{name}.cmd"):
        candidate = bindir / extra
        if candidate.is_file():
            return [str(candidate), *list(argv[1:])]
    return None


def spec_by_id(sid: str) -> LspServerSpec:
    for spec in CATALOG:
        if spec.id == sid:
            return spec
    raise KeyError(sid)


def jedi_available() -> bool:
    try:
        import jedi  # noqa: F401

        return True
    except ImportError:
        return False


def pyright_available() -> bool:
    return spec_ready(spec_by_id("python-pyright")) or spec_ready(spec_by_id("python-basedpyright"))


def python_lsp_ready() -> bool:
    return pyright_available() or spec_ready(spec_by_id("python-pylsp")) or jedi_available()


def spec_ready(spec: LspServerSpec) -> bool:
    if spec.backend == "jedi":
        return jedi_available()
    return which_argv(spec.argv) is not None


def resolve_lsp(path: Path, language: str = "") -> ResolvedLsp | None:
    language_id = language_id_for(path, language)
    suffix = path.suffix.lower()
    name = path.name.lower()
    if name == "dockerfile":
        suffix = ".dockerfile"
    for spec in CATALOG:
        if language_id in spec.language_ids or suffix in spec.suffixes:
            if spec.backend == "jedi" and jedi_available():
                return ResolvedLsp(spec=spec, argv=[], language_id=language_id, kind="jedi")
            resolved = which_argv(spec.argv)
            if resolved:
                return ResolvedLsp(spec=spec, argv=resolved, language_id=language_id, kind="lsp")
    return None


def install_hints(spec: LspServerSpec) -> list[str]:
    hints: list[str] = []
    for kind, value in spec.install:
        if kind == "extra":
            hints.append(f'pip install "Holix[{value}]"  # or: uv sync --extra {value}')
        elif kind == "pip":
            hints.append(f"pip install {value}")
        elif kind == "npm":
            hints.append(f"npm install -g {value}")
        elif kind == "go":
            hints.append(f"go install {value}")
        elif kind == "brew":
            hints.append(f"brew install {value}")
        elif kind == "apt":
            hints.append(f"sudo apt install {value}")
        elif kind == "rustup":
            hints.append(f"rustup {value}")
        elif kind == "cargo":
            hints.append(f"cargo install {value}")
        elif kind == "gem":
            hints.append(f"gem install {value}")
        else:
            hints.append(value)
    hints.append("Then: holix lsp setup   # or holix doctor")
    return hints


def hints_for_path(path: Path, language: str = "") -> list[str]:
    language_id = language_id_for(path, language)
    suffix = path.suffix.lower()
    for spec in CATALOG:
        if language_id in spec.language_ids or suffix in spec.suffixes:
            return install_hints(spec)
    return [
        "No language server is registered for this file type.",
        "Run: holix lsp status",
        "Fallback: grep",
    ]


def status_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in CATALOG:
        ready = spec_ready(spec)
        how = ""
        if ready and spec.backend == "jedi":
            how = "jedi (in-process)"
        elif ready:
            argv = which_argv(spec.argv) or []
            how = argv[0] if argv else " ".join(spec.argv)
        rows.append(
            {
                "id": spec.id,
                "title": spec.title,
                "ready": ready,
                "recommended": spec.recommended,
                "how": how,
                "install": install_hints(spec)[0] if spec.install else "",
            }
        )
    return rows


def ready_titles() -> list[str]:
    return [row["title"] for row in status_rows() if row["ready"]]


def missing_recommended() -> list[LspServerSpec]:
    return [spec for spec in CATALOG if spec.recommended and not spec_ready(spec)]
