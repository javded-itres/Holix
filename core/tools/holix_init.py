"""Tools optimized for `/init` — tiny LLM payloads, no full-file writes."""

from __future__ import annotations

from core.crypto.profile_crypto import ProfileCryptoLockedError
from core.project.holix_md import HOLIX_MD_FILENAME
from core.tools.base import BaseTool
from core.tools.execution_context import get_profile_name
from core.workspace import WorkspaceJailError, display_path_for_user, resolve_tool_path
from core.workspace.quota import WorkspaceQuotaExceeded
from core.workspace.storage import format_quota_error, write_profile_file_text


class UpdateHolixSectionTool(BaseTool):
    """Write one HOLIX.md section — keeps tool-call JSON small."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "update_holix_section"
        self.description = (
            "Update a single section in .holix/HOLIX.md by heading. "
            "Prefer this over patch_file/write_file during /init."
        )
        self.risk_level = "medium"
        self.parameters = {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to HOLIX.md (default: .holix/HOLIX.md)",
                    "default": ".holix/HOLIX.md",
                },
                "heading": {
                    "type": "string",
                    "description": "Section heading to replace, e.g. '## Overview'",
                },
                "content": {
                    "type": "string",
                    "description": "New markdown body for the section (max ~30 lines)",
                },
            },
            "required": ["heading", "content"],
        }

    async def execute(
        self,
        heading: str,
        content: str,
        path: str = ".holix/HOLIX.md",
    ) -> str:
        from core.project.holix_section import upsert_holix_section
        from core.tools.file_diff import read_file_text

        try:
            file_path = resolve_tool_path(path)
            if file_path.name not in (HOLIX_MD_FILENAME, "HELIX.md"):
                return "Error: update_holix_section only supports HOLIX.md"
            if not file_path.is_file():
                return f"Error: File '{path}' does not exist — run /init first"
            profile = get_profile_name()
            existing = read_file_text(file_path, profile=profile) or ""
            updated, err = upsert_holix_section(existing, heading=heading, content=content)
            if err:
                return f"Error: {err}"
            write_profile_file_text(file_path, updated, profile=profile)
            display_path = display_path_for_user(file_path, input_path=path)
            return f"Updated section {heading} in {display_path}"
        except WorkspaceQuotaExceeded as exc:
            return format_quota_error(exc)
        except WorkspaceJailError as exc:
            return f"Error: {exc}"
        except ProfileCryptoLockedError as exc:
            return f"Error: {exc}"
        except Exception as exc:
            return f"Error updating section: {exc}"


def register_holix_init_tools(registry) -> None:
    registry.register(UpdateHolixSectionTool())