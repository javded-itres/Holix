"""Project-local context (.holix/HOLIX.md) for Holix agents."""

from core.project.holix_md import (
    HOLIX_MD_FILENAME,
    HOLIX_MD_REL_PATH,
    append_holix_project_context,
    ensure_holix_dir,
    get_holix_md_path,
    holix_md_exists,
    load_holix_md,
    planning_context_note,
    task_context_note,
)
from core.project.init_prompt import build_init_user_message

__all__ = [
    "HOLIX_MD_FILENAME",
    "HOLIX_MD_REL_PATH",
    "append_holix_project_context",
    "build_init_user_message",
    "ensure_holix_dir",
    "get_holix_md_path",
    "holix_md_exists",
    "load_holix_md",
    "planning_context_note",
    "task_context_note",
]