"""Section updates for HOLIX.md during /init."""

from __future__ import annotations

import pytest
from core.project.holix_section import upsert_holix_section
from core.tools.holix_init import UpdateHolixSectionTool


def test_upsert_holix_section_replaces_body() -> None:
    text = "# Holix\n\n## Overview\n- Purpose:\n\n## Stack\n- Lang:\n"
    updated, err = upsert_holix_section(
        text,
        heading="## Overview",
        content="- Purpose: Demo monorepo\n- Users: internal team",
    )
    assert err is None
    assert "Demo monorepo" in updated
    assert "## Stack" in updated
    assert "- Lang:" in updated


@pytest.mark.asyncio
async def test_update_holix_section_tool(tmp_path) -> None:
    holix = tmp_path / ".holix" / "HOLIX.md"
    holix.parent.mkdir(parents=True, exist_ok=True)
    holix.write_text("## Overview\n- Purpose:\n", encoding="utf-8")
    tool = UpdateHolixSectionTool()
    result = await tool.execute(
        heading="## Overview",
        content="- Purpose: filled by tool",
        path=str(holix),
    )
    assert "Updated section" in result
    assert "filled by tool" in holix.read_text(encoding="utf-8")