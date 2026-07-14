"""User message for `/init` — scoped project analysis → `.holix/HOLIX.md`."""

from __future__ import annotations

from core.project.holix_md import HOLIX_MD_REL_PATH, ensure_holix_dir
from core.project.init_scan import InitProjectScan, format_init_scan_report, scan_project_for_init


def _holix_md_rel_path(target_dir: str | None = None) -> str:
    from core.project.holix_md import HOLIX_MD_FILENAME, HOLIX_MD_REL_PATH

    rel = (target_dir or "").strip().strip("/").replace("\\", "/")
    if not rel:
        return HOLIX_MD_REL_PATH
    return f"{rel}/.holix/{HOLIX_MD_FILENAME}"


def build_init_user_message(
    *,
    locale: str | None = None,
    profile_name: str | None = None,
    target_dir: str | None = None,
    scan: InitProjectScan | None = None,
) -> str:
    """Prompt sent to the agent when the user runs `/init`.

    Uses the profile UI locale (`/lang ru` | `/lang en`) so onboarding stays
    in the user's chosen language. A deterministic pre-scan keeps large repos
    within the agent read budget.
    """
    from core.i18n.locale import LocaleStore, normalize_locale
    from core.i18n.messages import t
    from core.prompt_builder import language_instruction_block

    loc = normalize_locale(locale)
    if profile_name and locale is None:
        loc = LocaleStore(profile_name).get()

    scope_rel = (target_dir or "").strip().strip("/").replace("\\", "/")
    ensure_holix_dir(scope_rel or None)
    holix_path = _holix_md_rel_path(scope_rel or None)
    if scan is None:
        scan = scan_project_for_init(target_dir=scope_rel or None)
    scan_report = format_init_scan_report(scan, locale=loc)
    template = t("init.holix_template", loc)
    lang_block = language_instruction_block(locale=loc, profile_name=profile_name)
    body = t(
        "init.user_message",
        loc,
        path=holix_path,
        template=template,
        scan_report=scan_report,
    )
    if scan.is_large:
        body = f"{t('init.large_hint', loc)}\n\n{body}"
    if scope_rel:
        scope = t("init.scope_dir", loc, dir=scope_rel)
        body = f"{scope}\n\n{body}"
    return f"{lang_block}\n\n{body}"