"""User message for `/init` — deep project analysis → `.holix/HOLIX.md`."""

from __future__ import annotations

from core.project.holix_md import HOLIX_MD_REL_PATH, ensure_holix_dir


def build_init_user_message(
    *,
    locale: str | None = None,
    profile_name: str | None = None,
) -> str:
    """Prompt sent to the agent when the user runs `/init`.

    Uses the profile UI locale (`/lang ru` | `/lang en`) so onboarding stays
    in the user's chosen language.
    """
    from core.i18n.locale import LocaleStore, normalize_locale
    from core.i18n.messages import t
    from core.prompt_builder import language_instruction_block

    loc = normalize_locale(locale)
    if profile_name and locale is None:
        loc = LocaleStore(profile_name).get()

    ensure_holix_dir()
    template = t("init.holix_template", loc)
    lang_block = language_instruction_block(locale=loc, profile_name=profile_name)
    body = t("init.user_message", loc, path=HOLIX_MD_REL_PATH, template=template)
    return f"{lang_block}\n\n{body}"