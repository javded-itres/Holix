#!/usr/bin/env python3
"""reg.ru DNS-01 helpers for certbot (no bash required inside Alpine).

Env:
  REGRU_USERNAME, REGRU_PASSWORD  — API credentials
  CERTBOT_DOMAIN, CERTBOT_VALIDATION — set by certbot for auth/cleanup
  REGRU_ZONE — optional zone (default: holix-agent.ru)
  ACME_DNS_WAIT_SEC — public NS wait (default 600)
  ACME_DNS_POLL_SEC — poll interval (default 15)
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API = "https://api.reg.ru/api/regru2"
ZONE_DEFAULT = "holix-agent.ru"


def die(msg: str, code: int = 1) -> None:
    print(f"regru_dns: ERROR: {msg}", file=sys.stderr, flush=True)
    raise SystemExit(code)


def log(msg: str) -> None:
    print(f"regru_dns: {msg}", flush=True)


def load_creds() -> tuple[str, str]:
    user = (os.environ.get("REGRU_USERNAME") or "").strip()
    password = (os.environ.get("REGRU_PASSWORD") or "").strip()
    if not user or not password:
        die("REGRU_USERNAME / REGRU_PASSWORD not set")
    return user, password


def zone_name() -> str:
    return (os.environ.get("REGRU_ZONE") or ZONE_DEFAULT).strip()


def subdomain_for_fqdn(fqdn: str, zone: str) -> str:
    fqdn = fqdn.rstrip(".").lower()
    zone = zone.rstrip(".").lower()
    if fqdn == zone:
        return "@"
    suffix = f".{zone}"
    if not fqdn.endswith(suffix):
        die(f"domain {fqdn!r} is outside zone {zone!r}")
    return fqdn[: -len(suffix)]


def api_call(method: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    user, password = load_creds()
    payload: dict[str, Any] = {
        "username": user,
        "password": password,
        "output_content_type": "json",
    }
    if extra:
        payload.update(extra)
    body = urllib.parse.urlencode(
        {
            "input_data": json.dumps(payload, ensure_ascii=False),
            "input_format": "json",
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{API}/{method}",
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        die(f"HTTP {e.code} from reg.ru {method}: {e.read()[:400]!r}")
    except Exception as e:
        die(f"request failed for {method}: {e}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        die(f"non-JSON from reg.ru {method}: {raw[:400]!r}")
    if data.get("result") != "success":
        die(f"reg.ru {method} failed: {raw[:800]}")
    return data


def list_txt(subdomain: str) -> list[dict[str, Any]]:
    data = api_call(
        "zone/get_resource_records",
        {
            "domains": [{"dname": zone_name()}],
            "output_content_type": "plain",
        },
    )
    # plain mode returns answer as list of domain blocks
    out: list[dict[str, Any]] = []
    answer = data.get("answer") or {}
    domains = answer.get("domains") if isinstance(answer, dict) else None
    if not domains and isinstance(answer, list):
        domains = answer
    if not domains:
        # try nested
        domains = (data.get("answer") or {}).get("domains") or []
    for block in domains or []:
        for rr in block.get("rrs") or []:
            if str(rr.get("rectype") or "").upper() != "TXT":
                continue
            if str(rr.get("subname") or "") != subdomain:
                continue
            out.append(rr)
    return out


def add_txt(subdomain: str, content: str) -> None:
    # remove existing identical / stale ACME tokens for this name first
    for rr in list_txt(subdomain):
        rid = rr.get("record_id")
        if rid is None:
            continue
        log(f"removing existing TXT {subdomain} id={rid}")
        api_call(
            "zone/remove_record",
            {
                "domains": [{"dname": zone_name()}],
                "record_id": int(rid),
                "content": rr.get("content") or "",
                "rectype": "TXT",
                "subdomain": subdomain,
            },
        )
        time.sleep(1)
    log(f"add TXT {subdomain}.{zone_name()} = {content[:16]}…")
    api_call(
        "zone/add_txt",
        {
            "domains": [{"dname": zone_name()}],
            "subdomain": subdomain,
            "text": content,
        },
    )


def remove_txt(subdomain: str, content: str) -> None:
    for rr in list_txt(subdomain):
        if str(rr.get("content") or "") != content:
            continue
        rid = rr.get("record_id")
        if rid is None:
            continue
        log(f"remove TXT {subdomain} id={rid}")
        api_call(
            "zone/remove_record",
            {
                "domains": [{"dname": zone_name()}],
                "record_id": int(rid),
                "content": content,
                "rectype": "TXT",
                "subdomain": subdomain,
            },
        )


def dig_txt(name: str) -> set[str]:
    """Resolve TXT via system resolver (usually recursive)."""
    try:
        import dns.resolver  # type: ignore

        answers = dns.resolver.resolve(name, "TXT")
        out: set[str] = set()
        for rdata in answers:
            # rdata.strings is list of bytes
            parts = getattr(rdata, "strings", None)
            if parts:
                out.add(b"".join(parts).decode("utf-8", errors="replace"))
            else:
                out.add(str(rdata).strip('"'))
        return out
    except Exception:
        pass
    # fallback: dig binary
    import subprocess

    for ns in ("8.8.8.8", "1.1.1.1", "ns1.reg.ru"):
        try:
            p = subprocess.run(
                ["dig", f"@{ns}", "+short", "TXT", name],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if p.returncode != 0 or not p.stdout.strip():
                continue
            vals: set[str] = set()
            for line in p.stdout.splitlines():
                line = line.strip().strip('"')
                if line:
                    vals.add(line.replace('" "', ""))
            if vals:
                return vals
        except Exception:
            continue
    return set()


def wait_public_txt(fqdn: str, token: str) -> None:
    wait = int(os.environ.get("ACME_DNS_WAIT_SEC") or "600")
    poll = int(os.environ.get("ACME_DNS_POLL_SEC") or "15")
    log(f"waiting up to {wait}s for public TXT {fqdn} (poll {poll}s)")
    deadline = time.time() + wait
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        vals = dig_txt(fqdn)
        if token in vals:
            log(f"public TXT OK after ~{attempt * poll}s: {fqdn}")
            return
        if vals:
            log(f"attempt {attempt}: found other TXT {list(vals)[:2]!r}, want token")
        else:
            log(f"attempt {attempt}: no TXT yet for {fqdn}")
        time.sleep(poll)
    die(
        f"TXT not public after {wait}s for {fqdn}. "
        f"Do NOT continue to Let's Encrypt — window would shift. "
        f"Increase ACME_DNS_WAIT_SEC or fix reg.ru propagation."
    )


def cmd_auth() -> None:
    domain = (os.environ.get("CERTBOT_DOMAIN") or "").strip()
    token = (os.environ.get("CERTBOT_VALIDATION") or "").strip()
    if not domain or not token:
        die("CERTBOT_DOMAIN / CERTBOT_VALIDATION required")
    zone = zone_name()
    challenge_fqdn = f"_acme-challenge.{domain}".rstrip(".")
    # for wildcard cert domain is *.preview.holix-agent.ru → challenge at
    # _acme-challenge.preview.holix-agent.ru
    if domain.startswith("*."):
        challenge_fqdn = f"_acme-challenge.{domain[2:]}".rstrip(".")
    sub = subdomain_for_fqdn(challenge_fqdn, zone)
    log(f"auth domain={domain} challenge={challenge_fqdn} sub={sub}")
    add_txt(sub, token)
    wait_public_txt(challenge_fqdn, token)
    # extra settle so LE multi-VA sees it
    settle = int(os.environ.get("ACME_DNS_SETTLE_SEC") or "30")
    log(f"settle {settle}s before certbot continues")
    time.sleep(settle)
    log("auth hook OK")


def cmd_cleanup() -> None:
    domain = (os.environ.get("CERTBOT_DOMAIN") or "").strip()
    token = (os.environ.get("CERTBOT_VALIDATION") or "").strip()
    if not domain:
        return
    zone = zone_name()
    challenge_fqdn = f"_acme-challenge.{domain}".rstrip(".")
    if domain.startswith("*."):
        challenge_fqdn = f"_acme-challenge.{domain[2:]}".rstrip(".")
    sub = subdomain_for_fqdn(challenge_fqdn, zone)
    if token:
        remove_txt(sub, token)
    else:
        for rr in list_txt(sub):
            rid = rr.get("record_id")
            if rid is None:
                continue
            api_call(
                "zone/remove_record",
                {
                    "domains": [{"dname": zone}],
                    "record_id": int(rid),
                    "content": rr.get("content") or "",
                    "rectype": "TXT",
                    "subdomain": sub,
                },
            )
    log("cleanup done")


def cmd_preflight() -> None:
    """Create a probe TXT, wait until public, remove. Exit 0 only if chain works."""
    zone = zone_name()
    token = f"holix-preflight-{int(time.time())}"
    # same label LE will use for *.preview
    challenge_fqdn = f"_acme-challenge.preview.{zone}"
    sub = subdomain_for_fqdn(challenge_fqdn, zone)
    log(f"PREFLIGHT start zone={zone} challenge={challenge_fqdn}")
    # credentials
    load_creds()
    api_call("user/nop")
    log("API auth OK")
    add_txt(sub, token)
    wait_public_txt(challenge_fqdn, token)
    remove_txt(sub, token)
    log("PREFLIGHT OK — safe to run certbot when LE window is open")


def cmd_list_acme() -> None:
    zone = zone_name()
    sub = subdomain_for_fqdn(f"_acme-challenge.preview.{zone}", zone)
    rrs = list_txt(sub)
    print(json.dumps(rrs, ensure_ascii=False, indent=2))


def main() -> None:
    if len(sys.argv) < 2:
        die("usage: regru_dns.py auth|cleanup|preflight|list-acme")
    cmd = sys.argv[1]
    if cmd == "auth":
        cmd_auth()
    elif cmd == "cleanup":
        cmd_cleanup()
    elif cmd == "preflight":
        cmd_preflight()
    elif cmd == "list-acme":
        cmd_list_acme()
    else:
        die(f"unknown command {cmd!r}")


if __name__ == "__main__":
    main()
