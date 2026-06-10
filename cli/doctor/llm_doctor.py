"""LLM-assisted profile config repair (doctor --fix only)."""

from __future__ import annotations

import json
import re
from typing import Any

import yaml
from core.models.manager import ModelManager
from openai import AsyncOpenAI

from cli.core import ProfileConfig, ProfileManager
from cli.doctor.findings import DoctorFinding
from cli.doctor.fixes import backup_config

DOCTOR_SYSTEM = """You are Helix Doctor, a configuration repair assistant.

You receive diagnostics about a broken Helix profile config.yaml and must output a CORRECTED
full YAML document only (no markdown fences, no commentary).

Required top-level fields (use sensible values from context):
- profile_name (string)
- model, base_url, api_key, temperature, max_steps
- data_dir, memory_db_path, vector_db_path, skills_dir
- providers (dict, optional), agent_models (dict, optional), default_provider (string, optional)

Preserve working values; fix only what diagnostics require.
Use OpenAI-compatible localhost defaults only when nothing else is known:
  base_url: http://localhost:11434/v1
  api_key: ollama
"""


def _extract_yaml(text: str) -> str:
    text = text.strip()
    fence = re.search(r"```(?:yaml)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    return text


async def llm_repair_profile(
    profile: str,
    findings: list[DoctorFinding],
) -> tuple[bool, str]:
    """Use default LLM to repair config.yaml. Returns (success, message)."""
    manager = ProfileManager()
    config_path = manager.get_profile_dir(profile) / "config.yaml"

    cfg = None
    raw_text = ""
    if config_path.exists():
        raw_text = config_path.read_text(encoding="utf-8")
        try:
            cfg = manager.load_profile(profile)
        except Exception:
            cfg = None

    mm = ModelManager(cfg) if cfg else ModelManager(
        ProfileConfig(profile_name=profile)
    )
    mc = mm.get_default_model_config()
    if mc is None or not mc.base_url:
        return False, "Cannot reach LLM: configure model/base_url first (helix models setup)"

    client = AsyncOpenAI(base_url=mc.base_url, api_key=mc.api_key or "dummy")
    model = mc.model or "gpt-4o-mini"

    issues = [
        {
            "code": f.code,
            "severity": f.severity,
            "title": f.title,
            "detail": f.detail,
            "recommendation": f.recommendation,
        }
        for f in findings
        if f.severity == "error" or f.code.startswith("profile.")
    ]

    user_prompt = (
        f"Profile: {profile}\n\n"
        f"Current config.yaml:\n```\n{raw_text or '(missing or empty)'}\n```\n\n"
        f"Diagnostics JSON:\n{json.dumps(issues, indent=2, ensure_ascii=False)}\n\n"
        "Output the fixed complete config.yaml content."
    )

    try:
        response = await client.chat.completions.create(
            model=model,
            temperature=0.1,
            messages=[
                {"role": "system", "content": DOCTOR_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
        )
    except Exception as e:
        return False, f"LLM repair failed: {e}"

    content = (response.choices[0].message.content or "").strip()
    if not content:
        return False, "LLM returned empty response"

    yaml_text = _extract_yaml(content)
    try:
        data: Any = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        return False, f"LLM output is not valid YAML: {e}"

    if not isinstance(data, dict):
        return False, "LLM output must be a YAML mapping"

    data["profile_name"] = profile
    try:
        repaired = ProfileConfig(**data)
    except Exception as e:
        return False, f"Repaired config failed validation: {e}"

    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists():
        backup = backup_config(config_path)
        backup_note = f" (backup: {backup})"
    else:
        backup_note = ""

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(repaired.model_dump(), f, default_flow_style=False)

    return True, f"Profile config repaired via LLM{backup_note}"


async def llm_remediation_advice(
    profile: str,
    findings: list[DoctorFinding],
) -> str | None:
    """Optional narrative advice when not fixing (read-only)."""
    errors = [f for f in findings if f.severity == "error"]
    if not errors:
        return None

    manager = ProfileManager()
    try:
        cfg = manager.load_profile(profile)
    except Exception:
        cfg = ProfileConfig(profile_name=profile)

    mm = ModelManager(cfg)
    mc = mm.get_default_model_config()
    if mc is None or not mc.base_url:
        return None

    client = AsyncOpenAI(base_url=mc.base_url, api_key=mc.api_key or "dummy")
    model = mc.model or "gpt-4o-mini"

    summary = "\n".join(f"- [{f.code}] {f.title}: {f.recommendation}" for f in errors[:12])

    try:
        response = await client.chat.completions.create(
            model=model,
            temperature=0.3,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Helix Doctor. Give a short numbered action plan (max 8 steps) "
                        "to fix Helix setup issues. Be concrete with CLI commands. Do not modify files."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Profile: {profile}\n\nIssues:\n{summary}",
                },
            ],
        )
    except Exception:
        return None

    return (response.choices[0].message.content or "").strip() or None