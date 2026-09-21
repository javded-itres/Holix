"""Install MikroLLM during Holix bootstrap and wire it as the LLM provider."""

from __future__ import annotations

import os
import re
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import httpx

DEFAULT_ADMIN = "http://127.0.0.1:4000"
DEFAULT_API = "http://127.0.0.1:4000/v1"
HUB_AUTO_MODEL = "auto"
DATA_DIR = Path.home() / ".mikrollm"
INSTALL_SH_URL = "https://raw.githubusercontent.com/javded-itres/mikrollm/main/scripts/install.sh"


@dataclass(frozen=True, slots=True)
class MikroLLMSetupResult:
    ok: bool
    admin_url: str = DEFAULT_ADMIN + "/admin"
    admin_password: str = ""
    api_base: str = DEFAULT_API
    api_key: str = ""
    hub_enabled: bool = False
    already_running: bool = False
    message: str = ""


def parse_csrf_token(html: str) -> str:
    m = re.search(
        r'<meta\s+name=["\']csrf-token["\']\s+content=["\']([^"\']+)["\']',
        html,
        re.I,
    )
    return (m.group(1).strip() if m else "") or ""


def parse_new_key(html: str) -> str:
    m = re.search(
        r'id=["\']new-key["\'][^>]*>(sk-[A-Za-z0-9_-]+)<',
        html,
        re.I,
    )
    if m:
        return m.group(1).strip()
    m = re.search(r"(sk-[A-Za-z0-9_-]{16,})", html)
    return m.group(1).strip() if m else ""


def read_admin_password(data_dir: Path | None = None) -> str:
    path = (data_dir or DATA_DIR) / "admin.pass"
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def gateway_health_ok(base: str = DEFAULT_ADMIN, timeout_s: float = 2.0) -> bool:
    url = urljoin(base.rstrip("/") + "/", "health")
    try:
        with httpx.Client(timeout=timeout_s) as client:
            resp = client.get(url)
            return resp.status_code == 200
    except httpx.HTTPError:
        return False


def wait_gateway(base: str = DEFAULT_ADMIN, *, attempts: int = 30, delay_s: float = 1.0) -> bool:
    for _ in range(max(1, attempts)):
        if gateway_health_ok(base):
            return True
        time.sleep(delay_s)
    return False


def install_mikrollm_binary(*, timeout_s: float = 600.0) -> tuple[bool, str]:
    """Run the official GitHub desktop installer (never a local clone)."""
    env = os.environ.copy()
    home_bin = str(Path.home() / ".local" / "bin")
    env["PATH"] = home_bin + os.pathsep + env.get("PATH", "")
    cmd = ["sh", "-c", f"curl -fsSL {INSTALL_SH_URL} | sh"]
    try:
        proc = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    log = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    if proc.returncode != 0:
        tail = log.strip()[-1500:] or f"exit {proc.returncode}"
        return False, tail
    return True, log.strip()[-1500:]


class MikroLLMAdmin:
    """Cookie + CSRF client for MikroLLM HTML admin (keys and hub)."""

    def __init__(self, base_url: str = DEFAULT_ADMIN, *, timeout_s: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=timeout_s, follow_redirects=True)

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> MikroLLMAdmin:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _url(self, path: str) -> str:
        return urljoin(self.base_url + "/", path.lstrip("/"))

    def login(self, password: str) -> None:
        resp = self.client.post(self._url("/admin/login"), data={"password": password})
        if resp.status_code >= 400:
            raise RuntimeError(f"admin login HTTP {resp.status_code}")
        if "/admin/login" in str(resp.url):
            raise RuntimeError("admin login failed (bad password)")

    def _csrf(self) -> str:
        html = self.client.get(self._url("/admin")).text
        token = parse_csrf_token(html)
        if not token:
            raise RuntimeError("CSRF token not found on /admin")
        return token

    def create_key(self, *, name: str = "holix", rpm: int = 0) -> str:
        csrf = self._csrf()
        resp = self.client.post(
            self._url("/admin/keys"),
            data={
                "csrf": csrf,
                "name": name,
                "rpm": str(rpm),
                "all_models": "1",
            },
            headers={"X-CSRF-Token": csrf},
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"create key HTTP {resp.status_code}")
        key = parse_new_key(resp.text)
        if not key:
            raise RuntimeError("created key not shown (flash expired or HTML changed)")
        return key

    def enable_hub(self, *, name: str | None = None) -> None:
        csrf = self._csrf()
        node = (name or socket.gethostname() or "holix").strip() or "holix"
        resp = self.client.post(
            self._url("/admin/hub"),
            data={
                "csrf": csrf,
                "enabled": "1",
                "name": node[:64],
            },
            headers={"X-CSRF-Token": csrf},
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"enable hub HTTP {resp.status_code}")


def provision_mikrollm(
    *,
    install: bool = True,
    key_name: str = "holix",
    hub_name: str | None = None,
) -> MikroLLMSetupResult:
    """Install if needed, issue an sk- key, enable hub member, return credentials."""
    was_running = gateway_health_ok()
    running = was_running
    if install and not running:
        ok, log = install_mikrollm_binary()
        if not ok:
            return MikroLLMSetupResult(ok=False, message=log or "MikroLLM install failed")
        if not wait_gateway():
            return MikroLLMSetupResult(
                ok=False,
                message="MikroLLM installed but /health did not answer on :4000",
            )
        running = True

    if not running:
        return MikroLLMSetupResult(
            ok=False,
            already_running=was_running,
            message="MikroLLM is not running on http://127.0.0.1:4000",
        )

    password = read_admin_password()
    if not password:
        return MikroLLMSetupResult(
            ok=False,
            already_running=was_running,
            message="MikroLLM is up but ~/.mikrollm/admin.pass is missing",
        )

    existing = (os.environ.get("MIKROLLM_API_KEY") or "").strip()
    api_key = existing if existing.startswith("sk-") else ""
    hub_ok = False
    err = ""
    try:
        with MikroLLMAdmin() as admin:
            admin.login(password)
            if not api_key:
                api_key = admin.create_key(name=key_name)
            try:
                admin.enable_hub(name=hub_name)
                hub_ok = True
            except RuntimeError as exc:
                err = str(exc)
    except RuntimeError as exc:
        return MikroLLMSetupResult(
            ok=False,
            already_running=was_running,
            admin_password=password,
            message=str(exc),
        )

    if not api_key:
        return MikroLLMSetupResult(
            ok=False,
            already_running=was_running,
            admin_password=password,
            hub_enabled=hub_ok,
            message=err or "could not create API key",
        )
    return MikroLLMSetupResult(
        ok=True,
        already_running=was_running,
        admin_password=password,
        api_key=api_key,
        hub_enabled=hub_ok,
        message=err,
    )


def apply_mikrollm_auto_model(config: object) -> None:
    """Point the Holix agent at MikroLLM hub alias ``auto``."""
    config.default_provider = "mikrollm"
    config.model = HUB_AUTO_MODEL
    providers = dict(getattr(config, "providers", None) or {})
    pdata = dict(providers.get("mikrollm") or {})
    if pdata:
        available = [
            str(m).strip() for m in (pdata.get("available_models") or []) if str(m).strip()
        ]
        if HUB_AUTO_MODEL not in available:
            available.insert(0, HUB_AUTO_MODEL)
        pdata["available_models"] = available
        pdata["default_model"] = HUB_AUTO_MODEL
        providers["mikrollm"] = pdata
        config.providers = providers
    agent_models = dict(getattr(config, "agent_models", None) or {})
    temp = float(getattr(config, "temperature", 0.7) or 0.7)
    agent_models["main"] = {
        "agent_name": "main",
        "provider": "mikrollm",
        "model": HUB_AUTO_MODEL,
        "temperature": temp,
        "max_tokens": None,
        "metadata": {},
    }
    config.agent_models = agent_models


def store_mikrollm_env(api_key: str, api_base: str = DEFAULT_API) -> None:
    """Persist MIKROLLM_API_KEY / MIKROLLM_API_BASE in Holix global .env."""
    from cli.installer.bootstrap import _global_env_path, _upsert_env_var

    if api_key:
        _upsert_env_var(_global_env_path(), "MIKROLLM_API_KEY", api_key)
        os.environ["MIKROLLM_API_KEY"] = api_key
    if api_base:
        _upsert_env_var(_global_env_path(), "MIKROLLM_API_BASE", api_base)
        os.environ["MIKROLLM_API_BASE"] = api_base
