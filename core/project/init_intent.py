"""Natural-language Holix init → same path as ``/init``."""

from __future__ import annotations

import re
from typing import Any

_INIT_RE = re.compile(
    r"(?is)("
    r"инициализац\w*\s+holix"
    r"|holix\s+init"
    r"|init(?:ialize|ialise)?\s+holix"
    r"|/init\b"
    r"|holix\.md"
    r"|справ[оа]чник\s+holix"
    r"|holix\s+handbook"
    r")"
)

_ALREADY_INIT_PROMPT = "update_holix_section"


def looks_like_holix_init_request(text: str) -> bool:
    raw = (text or "").strip()
    if not raw or _ALREADY_INIT_PROMPT in raw:
        return False
    return bool(_INIT_RE.search(raw))


def expand_user_message_for_holix_init(
    text: str,
    *,
    agent: Any | None = None,
    locale: str | None = None,
    profile_name: str | None = None,
    cwd: str | None = None,
) -> str:
    """Prepend the ``/init`` user prompt when the message asks to init Holix.

    Mixed requests keep the original text after the init checklist. Already
    expanded prompts are left unchanged. ``HOLIX.md`` skeleton is created when
    missing (same as ``run_project_init``).
    """
    raw = (text or "").strip()
    if not looks_like_holix_init_request(raw):
        return text

    from core.i18n.locale import LocaleStore, normalize_locale
    from core.i18n.messages import t
    from core.project.holix_md import HOLIX_MD_FILENAME
    from core.project.init_prompt import _holix_md_rel_path, build_init_user_message
    from core.project.init_scan import scan_project_for_init, write_init_skeleton
    from core.project.workspace_root import resolve_project_root

    loc = normalize_locale(locale)
    cfg = getattr(agent, "config", None) if agent is not None else None
    profile = profile_name or getattr(cfg, "profile_name", None)
    if profile and locale is None:
        loc = LocaleStore(str(profile)).get()

    project_root = cwd or resolve_project_root(agent=agent, config=cfg)
    scan = scan_project_for_init(cwd=project_root)
    holix_path = _holix_md_rel_path(None)
    skeleton = scan.scope_root / ".holix" / HOLIX_MD_FILENAME
    if not skeleton.is_file():
        template = t("init.holix_template", loc)
        write_init_skeleton(
            scan,
            holix_rel_path=holix_path,
            template=template,
            locale=loc,
        )

    init_prompt = build_init_user_message(
        locale=loc,
        profile_name=profile,
        scan=scan,
        cwd=project_root,
    )
    stripped_lower = raw.lower()
    if stripped_lower in {"/init", "init", "holix init"} or re.fullmatch(
        r"(?is)сделай\s+инициализац\w*\s+holix\.?",
        raw,
    ):
        return init_prompt
    return (
        f"{init_prompt}\n\n---\n"
        "The user's original request (do this as well after the handbook "
        "sections exist):\n"
        f"{raw}"
    )
