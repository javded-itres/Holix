"""Classify shell commands as a one-shot job vs a long-running service.

Regex can never cover every language and wrapper. Two layers:

1. **Static** — high-confidence launch verbs at a *segment head*
   (``cargo run``, ``go run``, ``java -jar``, ``dotnet run``, …).
   Mentions inside ``grep`` / ``pip list`` are ignored.
2. **Runtime** — after the process has been running for ~60s, look at the
   process tree. A TCP LISTEN socket is the language-agnostic signal that
   this is a server, not ``cargo test`` / ``mvn package`` / a long compile.

A long job that never binds (train loop, ``sleep``, hung compile) is left
alone. A pytest suite that happens to bind a fixture port is treated as a
one-shot and is not promoted.
"""

from __future__ import annotations

import os
import re
import subprocess

from core.platform_compat import IS_WINDOWS

# Default: give compiles / test suites a minute before we peek inside.
_DEFAULT_WATCH_AFTER = 60.0
_DEFAULT_WATCH_INTERVAL = 10.0

# Prefixes that are not the launched binary (env, wrappers).
_LAUNCH_PREFIX = re.compile(
    r"^(?:"
    r"[\w.]+=\S+\s+"
    r"|export\s+[\w.]+=\S+\s+"
    r"|sudo\s+(?:-\w\s+)*"
    r"|nohup\s+"
    r"|exec\s+"
    r"|command\s+"
    r"|time\s+"
    r"|nice\s+"
    r"|env\s+(?:-[\w]+\s+|[\w.]+=\S+\s+)*"
    r"|uv\s+run\s+(?:--\S+\s+)*"
    r"|poetry\s+run\s+"
    r"|pipenv\s+run\s+"
    r"|hatch\s+run\s+"
    r"|pdm\s+run\s+"
    r"|bundle\s+exec\s+"
    r")*",
    re.I,
)

# Segments that only inspect / filter / build / test — never a server start.
_INSPECT_HEAD = re.compile(
    r"^(?:"
    r"grep|egrep|fgrep|rg|ag|ack|"
    r"head|tail|wc|cat|less|more|bat|"
    r"awk|sed|cut|sort|uniq|tr|"
    r"echo|printf|"
    r"which|type|whereis|"
    r"ls|lsof|pgrep|pkill|kill|killall|fuser|"
    r"ps|top|htop|"
    r"pip\d*\s+(?:list|show|freeze|index|search|install|uninstall)|"
    r"python\d*\s+-m\s+pip\s+"
    r"(?:list|show|freeze|index|search|install)|"
    r"uv\s+pip\s+(?:list|show|freeze|install)|"
    r"(?:npm|pnpm|yarn)\s+(?:ls|list|install|ci|"
    r"(?:run\s+)?(?:test|build|lint|typecheck|check|ci))\b|"
    r"npx\s+(?:tsc|eslint|jest|vitest|prettier)\b|"
    r"ruff|pytest|py\.test|mypy|black|isort|coverage|"
    r"tox\b|nox\b|hatch\s+test\b|"
    r"bun\s+test\b|deno\s+test\b|"
    r"python\d*\s+-m\s+(?:pytest|unittest|mypy|ruff|compileall)\b|"
    r"python\d*(?:\s+-\S+)*\s+\S*test[^/\s]*\.py\b|"
    r"cargo\s+(?:-\S+\s+)*(?:build|test|check|clippy|fmt|bench|doc|clean|update|fetch)\b|"
    r"go\s+(?:-\S+\s+)*(?:test|build|vet|fmt|mod|generate|install)\b|"
    r"(?:[\w./-]+/)?(?:mvn|mvnw)\b(?!.*(?:spring-boot:run|quarkus:dev))"
    r".*\b(?:test|package|compile|install|verify|clean|dependency:)\b|"
    r"(?:[\w./-]+/)?gradlew?\s+(?:-\S+\s+)*(?:test|build|check|assemble|clean)\b|"
    r"dotnet\s+(?:-\S+\s+)*(?:test|build|restore|publish|clean|pack)\b|"
    r"cmake\b|ctest\b|"
    r"(?:g\+\+|gcc|clang\+\+|clang|rustc|javac)(?:\s|$)|"
    r"make\s+(?:all|test|check|clean|install|build)\b"
    r")",
    re.I,
)

# Launch verb at the start of a segment (after prefixes).
_LAUNCH_HEAD = re.compile(
    r"^(?:"
    r"(?:[\w./-]+/)?(?:uvicorn|gunicorn|hypercorn|daphne)\b|"
    r"python\d*\s+-m\s+uvicorn\b|"
    r"python\d*\s+-m\s+http\.server\b|"
    r"python\d*\s+-m\s+(?!pip\b|pytest\b|ruff\b|venv\b|compileall\b|http\.server\b)"
    r"[\w.]+\.main\b|"
    r"python\d*(?:\s+-\w+(?:=\S+)?)*\s+(?!-m\b)(?:\./|\S+/)?main\.py\b|"
    r"python\d*\s+\S*manage\.py\s+runserver\b|"
    r"fastapi\s+run\b|"
    r"flask\s+run\b|"
    r"(?:npm|pnpm|yarn)\s+(?:run\s+)?(?:dev|start|serve)\b|"
    r"next\s+dev\b|"
    r"nuxt\s+dev\b|"
    r"vite\b(?!\s+build\b)|"
    r"nodemon\b|"
    r"python\d*\s+\S*bot\.py\b|"
    r"python\d*\s+-m\s+integrations\.telegram\b|"
    r"telegram_channel_publisher\b|"
    # Rust / Go / Java / C# / JVM build tools / PHP / Ruby / Elixir
    r"cargo\s+run\b|"
    r"cargo\s+watch\b|"
    r"go\s+run\b|"
    r"java\s+(?:-\S+\s+)*-jar\b|"
    r"(?:[\w./-]+/)?(?:mvn|mvnw)\s+.*spring-boot:run\b|"
    r"(?:[\w./-]+/)?(?:mvn|mvnw)\s+.*quarkus:dev\b|"
    r"(?:[\w./-]+/)?gradlew?\s+.*bootRun\b|"
    r"(?:[\w./-]+/)?gradlew?\s+.*quarkusDev\b|"
    r"dotnet\s+run\b|"
    r"dotnet\s+watch\b|"
    r"php\s+artisan\s+serve\b|"
    r"php\s+-S\b|"
    r"(?:bundle\s+exec\s+)?(?:rails\s+(?:s|server)\b|puma\b|rackup\b)|"
    r"mix\s+phx\.server\b|"
    r"hugo\s+server\b|"
    r"jekyll\s+serve\b|"
    r"caddy\s+run\b"
    r")",
    re.I,
)

_COMPOSE_UP = re.compile(
    r"^(?:[\w./-]+/)?docker(?:-compose|\s+compose)\s+up\b",
    re.I,
)
_COMPOSE_DETACH = re.compile(r"(?:^|\s)(?:-d|--detach)\b", re.I)

_LSOF_LISTEN_PORT = re.compile(r":(\d{2,5})(?:\s+\(LISTEN\)|\s|$)")


def service_watch_after() -> float:
    raw = os.environ.get("HOLIX_SERVICE_WATCH_AFTER")
    if raw and str(raw).strip():
        try:
            return max(0.05, float(raw))
        except ValueError:
            pass
    return _DEFAULT_WATCH_AFTER


def service_watch_interval() -> float:
    raw = os.environ.get("HOLIX_SERVICE_WATCH_INTERVAL")
    if raw and str(raw).strip():
        try:
            return max(0.05, float(raw))
        except ValueError:
            pass
    return _DEFAULT_WATCH_INTERVAL


def split_shell_segments(command: str) -> list[str]:
    """Split on ; && || | & newline, keeping quoted spans intact."""
    parts: list[str] = []
    buf: list[str] = []
    quote = ""
    i = 0
    text = command or ""
    while i < len(text):
        ch = text[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = ""
            i += 1
            continue
        if ch in {"'", '"'}:
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch == "\n" or ch == ";":
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        if ch == "&" and i + 1 < len(text) and text[i + 1] == "&":
            parts.append("".join(buf))
            buf = []
            i += 2
            continue
        if ch == "|" and i + 1 < len(text) and text[i + 1] == "|":
            parts.append("".join(buf))
            buf = []
            i += 2
            continue
        if ch in {"|", "&"}:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def segment_head(segment: str) -> str:
    """Drop env assignments / wrappers so the real binary is first."""
    text = (segment or "").strip()
    while True:
        nxt = _LAUNCH_PREFIX.sub("", text, count=1)
        if nxt == text:
            break
        text = nxt.lstrip()
    return text


def _is_compose_up_foreground(head: str) -> bool:
    return bool(_COMPOSE_UP.match(head) and not _COMPOSE_DETACH.search(head))


def _is_launch_head(head: str) -> bool:
    if not head:
        return False
    if _LAUNCH_HEAD.match(head):
        return True
    return _is_compose_up_foreground(head)


def is_untracked_long_running_command(command: str) -> bool:
    """True when some *executable segment* starts a server/bot.

    Quoted strings, grep patterns, and ``pip list`` are ignored so mentioning
    ``uvicorn`` is not treated as launching it.
    """
    for raw in split_shell_segments(command or ""):
        head = segment_head(raw)
        if not head or _INSPECT_HEAD.match(head):
            continue
        if _is_launch_head(head):
            return True
    return False


_TEST_BUILD_TOKEN = re.compile(
    r"(?i)\b("
    r"pytest|py\.test|unittest|tox|nox|"
    r"jest|vitest|cypress|playwright|mocha|"
    r"cargo\s+test|go\s+test|dotnet\s+test|"
    r"mvn\s+\S*test|gradlew?\s+\S*test|"
    r"npm\s+(?:run\s+)?test|pnpm\s+(?:run\s+)?test|yarn\s+(?:run\s+)?test|"
    r"coverage\s+run"
    r")\b"
)


def is_test_or_build_command(command: str) -> bool:
    """True for pytest / npm test / cargo test / builds — never a background service."""
    if is_long_oneshot_job(command):
        return True
    text = (command or "").strip()
    if not text:
        return False
    if is_untracked_long_running_command(text):
        return False
    return bool(_TEST_BUILD_TOKEN.search(text))


def is_long_oneshot_job(command: str) -> bool:
    """True when every real segment is a build/test/inspect command.

    Used by the runtime watchdog so ``cargo test`` / ``mvn package`` that
    happen to bind a fixture port are not promoted to a background service.
    """
    saw_any = False
    for raw in split_shell_segments(command or ""):
        head = segment_head(raw)
        if not head:
            continue
        saw_any = True
        if _INSPECT_HEAD.match(head):
            continue
        return False
    return saw_any


def _pid_tree(root_pid: int) -> list[int]:
    if root_pid <= 0:
        return []
    found = [root_pid]
    seen = {root_pid}
    try:
        import psutil

        proc = psutil.Process(root_pid)
        for child in proc.children(recursive=True):
            if child.pid not in seen:
                seen.add(child.pid)
                found.append(child.pid)
        return found
    except Exception:
        pass

    queue = [root_pid]
    while queue:
        parent = queue.pop()
        try:
            result = subprocess.run(
                ["pgrep", "-P", str(parent)],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            break
        for token in (result.stdout or "").split():
            if not token.isdigit():
                continue
            pid = int(token)
            if pid in seen:
                continue
            seen.add(pid)
            found.append(pid)
            queue.append(pid)
    return found


def _ports_from_lsof_text(text: str) -> list[int]:
    ports: list[int] = []
    seen: set[int] = set()
    for line in (text or "").splitlines():
        if line.startswith("COMMAND"):
            continue
        for match in _LSOF_LISTEN_PORT.finditer(line):
            try:
                port = int(match.group(1))
            except (TypeError, ValueError):
                continue
            if 1 <= port <= 65535 and port not in seen:
                seen.add(port)
                ports.append(port)
    return ports


def listen_ports_for_pid_tree(root_pid: int) -> list[int]:
    """TCP LISTEN ports owned by ``root_pid`` or any descendant (best effort)."""
    if root_pid <= 0 or IS_WINDOWS:
        return []
    pids = _pid_tree(root_pid) or [root_pid]
    pid_csv = ",".join(str(p) for p in pids[:64])
    try:
        result = subprocess.run(
            ["lsof", "-nP", "-a", "-p", pid_csv, "-iTCP", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        ports = _ports_from_lsof_text(result.stdout or "")
        if ports:
            return ports
    except (OSError, subprocess.SubprocessError):
        pass

    # Fallback: all listeners, keep rows whose PID is in our tree.
    tree = set(pids)
    try:
        result = subprocess.run(
            ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    ports: list[int] = []
    seen: set[int] = set()
    for line in (result.stdout or "").splitlines():
        if line.startswith("COMMAND"):
            continue
        cols = line.split()
        if len(cols) < 2 or not cols[1].isdigit():
            continue
        if int(cols[1]) not in tree:
            continue
        for match in _LSOF_LISTEN_PORT.finditer(line):
            try:
                port = int(match.group(1))
            except (TypeError, ValueError):
                continue
            if 1 <= port <= 65535 and port not in seen:
                seen.add(port)
                ports.append(port)
    return ports


def should_promote_foreground_service(
    command: str,
    *,
    pid: int,
    elapsed_s: float,
    listen_ports: list[int] | None = None,
) -> tuple[bool, list[int]]:
    """Decide whether a still-running foreground command is a service.

    ``listen_ports`` may be injected by tests. Otherwise the live process
    tree is inspected.
    """
    if elapsed_s < service_watch_after():
        return False, []
    if is_long_oneshot_job(command):
        return False, []
    ports = list(listen_ports) if listen_ports is not None else listen_ports_for_pid_tree(pid)
    if ports:
        return True, ports
    return False, []
