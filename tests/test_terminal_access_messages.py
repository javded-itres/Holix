"""Clear access-denied messages from run_terminal_command."""

from __future__ import annotations

from pathlib import Path

from core.tools.terminal import (
    _blocked_sensitive_path_access,
    _format_access_denial,
    _format_process_result,
    _is_untracked_long_running_command,
)


def test_pip_install_uvicorn_is_not_a_server_launch() -> None:
    not_launch = [
        (
            "cd projects/data_address && python -m venv .venv && "
            "source .venv/bin/activate && pip install fastapi uvicorn pydantic dishka"
        ),
        "uv pip install uvicorn",
        "python -m pytest tests",
        "uv run pytest -q",
        "poetry run pytest",
        "python -m ruff check .",
        (
            "cd projects/data_address && source .venv/bin/activate && "
            "python -m pip list | grep -iE 'fastapi|dadata|dishka|pydantic|uvicorn|httpx|pytest'"
        ),
        "grep -R uvicorn projects/",
        "ps aux | grep uvicorn",
        "lsof -ti:8000 | xargs kill -9",
        "echo uvicorn app:app",
        "cat README.md | grep uvicorn",
        "python tests/test_main.py",
        "python -m compileall src",
        "timeout 2 curl -s http://127.0.0.1:8000/health",
        "cargo test",
        "cargo build --release",
        "go test ./...",
        "go build -o bin/app ./cmd/app",
        "mvn -q test",
        "mvn package -DskipTests",
        "./gradlew test",
        "dotnet test",
        "dotnet build",
        "cmake --build build",
        "g++ -O2 main.cpp -o app",
        "npm run build",
        "pnpm test",
        "docker compose up -d",
        "docker-compose up --detach",
    ]
    launch = [
        "uvicorn app:app --port 8000",
        "python -m uvicorn app.main:app",
        "pip install uvicorn && uvicorn app:app --reload",
        "cd projects/data_address && PYTHONPATH=src python -m data_address.main",
        "python app/main.py --port 8000",
        "nohup uvicorn app:app --reload",
        "fastapi run app.py",
        "npm run dev",
        "pnpm dev",
        "npm start",
        "./.venv/bin/uvicorn app:app",
        "cargo run --release --bin api",
        "go run ./cmd/server",
        "java -jar app.jar --server.port=8080",
        "java -Xmx512m -jar target/app.jar",
        "mvn spring-boot:run",
        "./mvnw spring-boot:run",
        "./gradlew bootRun",
        "dotnet run --project src/Api",
        "dotnet watch run",
        "php artisan serve --port=8000",
        "php -S 127.0.0.1:8080",
        "rails server",
        "bundle exec puma",
        "mix phx.server",
        "docker compose up",
        "docker-compose up --build",
        "python manage.py runserver 0.0.0.0:8000",
    ]
    for cmd in not_launch:
        assert _is_untracked_long_running_command(cmd) is False, cmd
    for cmd in launch:
        assert _is_untracked_long_running_command(cmd) is True, cmd


def test_sudo_denied_is_human_readable() -> None:
    msg = _format_process_result(
        returncode=1,
        output="",
        error="sudo: I'm sorry holix. I'm afraid I can't do that",
    )
    assert "нет прав" in msg.lower() or "прав" in msg
    assert "sudo" in msg.lower() or "root" in msg.lower()
    assert "STDOUT" in msg


def test_permission_denied_path() -> None:
    msg = _format_access_denial(
        returncode=1,
        output="",
        error="bash: /root/secret: Permission denied",
    )
    assert msg is not None
    assert "прав" in msg.lower() or "permission" in msg.lower()


def test_own_workspace_allowed_when_jail_off(tmp_path: Path) -> None:
    """Admin (jail off) must still be able to write into its own workspace path."""
    profile = tmp_path / "profiles" / "admin"
    workspace = profile / "workspace"
    workspace.mkdir(parents=True)
    ws = str(workspace.resolve())
    blocked, reason = _blocked_sensitive_path_access(
        f"mv /tmp/foo {ws}/bar",
        jail_enabled=False,
        workspace_root=ws,
    )
    assert not blocked, reason
    # Secrets next to workspace still blocked
    blocked, _ = _blocked_sensitive_path_access(
        f"cat {profile.resolve()}/.env",
        jail_enabled=False,
        workspace_root=ws,
    )
    assert blocked


def test_profile_tree_blocked_when_no_workspace_root() -> None:
    blocked, reason = _blocked_sensitive_path_access(
        "ls /var/lib/holix/profiles/admin/workspace",
        jail_enabled=False,
        workspace_root=None,
    )
    assert blocked
    assert "profile" in reason.lower() or "secret" in reason.lower()
