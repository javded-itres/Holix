from typing import Any

from openai import AsyncOpenAI


class SkillGenerator:
    """Generates new skills from successful agent sessions."""

    def __init__(self, llm_client: AsyncOpenAI, *, model: str):
        self.client = llm_client
        self.model = (model or "").strip()
        if not self.model:
            raise ValueError(
                "SkillGenerator requires an active agent model (profile default), not global settings."
            )

    async def create_skill_from_session(
        self,
        messages: list[dict[str, Any]],
        task_description: str,
        *,
        existing_names: list[str] | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Generate a new skill from a successful session.

        Args:
            messages: Conversation messages
            task_description: Description of the task that was solved

        Returns:
            Dictionary containing skill metadata and content
        """
        # Build conversation summary for the LLM
        conversation_summary = self._build_conversation_summary(messages)

        existing = ", ".join((existing_names or [])[:80]) or "(none)"
        lang = (locale or "en").strip().lower()
        lang_name = "Russian" if lang.startswith("ru") else "English"
        prompt = f"""You just successfully completed this task: {task_description}

Here's the conversation history:

{conversation_summary}

Existing skills (reuse or patch one of these if this is the same pattern):
{existing}

Decide whether this session should become a reusable skill.
Prefer ACTION: reuse or patch over create.
Do NOT invent a new name for a slight variation of an existing skill.
Do NOT create greeting, persona, status-check, or one-off project diary skills.
Do NOT encode a transient failure (timeout, 429, network blip) as "never use this tool".
Write DESCRIPTION and all markdown sections in {lang_name}.

Provide your response in this exact format:

ACTION: reuse | patch | create | refuse
SKILL_NAME: (existing name for reuse/patch, or a_snake_case name for create)
REFUSE_REASON: (only if ACTION is refuse: transient_failure | junk | too_narrow | already_covered)
DESCRIPTION: (brief one-line description in {lang_name}, ≤ 80 characters)
QUALITY_SCORE: (integer 1-100 — honest quality of this as a reusable procedure.
1-19 found, 20-39 bronze, 40-59 silver, 60-79 gold auto-approve, 80-100 epic auto-approve)
TAGS: (comma-separated tags, e.g., python, web, fastapi)

WHEN_TO_USE:
(trigger conditions — when the agent should load this skill)

PROCEDURE:
1. Step one with concrete Holix tools
2. Step two

PITFALLS:
- Reproducible traps only, not one-off timeouts

VERIFICATION:
How to confirm it worked.

EXAMPLES:
- (example use case 1)
- (example use case 2)
"""

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at analyzing successful task completions and creating reusable skills.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )

        skill_text = response.choices[0].message.content

        # Parse the skill response
        skill_data = self._parse_skill_response(skill_text)

        return skill_data

    def _build_conversation_summary(self, messages: list[dict[str, Any]]) -> str:
        """Build a summary of the conversation for skill generation.

        Args:
            messages: List of conversation messages

        Returns:
            Formatted conversation summary
        """
        summary_parts = []

        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            if not content:
                continue

            if role == "user":
                summary_parts.append(f"USER: {content}")
            elif role == "assistant":
                # Truncate long assistant messages
                truncated = content[:500] + "..." if len(content) > 500 else content
                summary_parts.append(f"ASSISTANT: {truncated}")
            elif role == "tool":
                # Include tool results but truncated
                truncated = content[:200] + "..." if len(content) > 200 else content
                summary_parts.append(f"TOOL_RESULT: {truncated}")

        return "\n\n".join(summary_parts)

    def _parse_skill_response(self, response: str) -> dict[str, Any]:
        """Parse the LLM's skill generation response.

        Args:
            response: Raw LLM response

        Returns:
            Parsed skill data
        """
        lines = response.strip().split("\n")

        skill_data = {
            "action": "create",
            "name": "unnamed_skill",
            "description": "",
            "tags": [],
            "content": "",
            "examples": [],
            "refuse_reason": "",
            "quality_score": 0,
            "when_to_use": "",
            "procedure": "",
            "pitfalls": "",
            "verification": "",
        }

        current_section = None
        buckets: dict[str, list[str]] = {
            "content": [],
            "examples": [],
            "when": [],
            "procedure": [],
            "pitfalls": [],
            "verification": [],
        }

        for line in lines:
            upper = line.strip().upper()
            if line.startswith("ACTION:"):
                action = line.replace("ACTION:", "", 1).strip().lower()
                if action in {"reuse", "patch", "create", "refuse"}:
                    skill_data["action"] = action
            elif line.startswith("SKILL_NAME:"):
                skill_data["name"] = line.replace("SKILL_NAME:", "", 1).strip()
            elif line.startswith("REFUSE_REASON:"):
                skill_data["refuse_reason"] = line.replace("REFUSE_REASON:", "", 1).strip()
            elif line.startswith("QUALITY_SCORE:"):
                from core.skills.quality import clamp_score

                skill_data["quality_score"] = clamp_score(
                    line.replace("QUALITY_SCORE:", "", 1).strip()
                )
            elif line.startswith("DESCRIPTION:"):
                skill_data["description"] = line.replace("DESCRIPTION:", "", 1).strip()
            elif line.startswith("TAGS:"):
                tags_str = line.replace("TAGS:", "", 1).strip()
                skill_data["tags"] = [t.strip() for t in tags_str.split(",") if t.strip()]
            elif upper in {
                "CONTENT:",
                "WHEN_TO_USE:",
                "PROCEDURE:",
                "PITFALLS:",
                "VERIFICATION:",
                "EXAMPLES:",
            }:
                current_section = {
                    "CONTENT:": "content",
                    "WHEN_TO_USE:": "when",
                    "PROCEDURE:": "procedure",
                    "PITFALLS:": "pitfalls",
                    "VERIFICATION:": "verification",
                    "EXAMPLES:": "examples",
                }[upper]
            else:
                if current_section == "examples":
                    if line.strip().startswith("-"):
                        buckets["examples"].append(line.strip()[1:].strip())
                elif current_section:
                    buckets[current_section].append(line)

        skill_data["when_to_use"] = "\n".join(buckets["when"]).strip()
        skill_data["procedure"] = "\n".join(buckets["procedure"]).strip()
        skill_data["pitfalls"] = "\n".join(buckets["pitfalls"]).strip()
        skill_data["verification"] = "\n".join(buckets["verification"]).strip()
        skill_data["examples"] = buckets["examples"]
        assembled = self._assemble_content(skill_data)
        raw_content = "\n".join(buckets["content"]).strip()
        skill_data["content"] = assembled or raw_content
        if not skill_data.get("quality_score"):
            from core.skills.quality import heuristic_quality

            skill_data["quality_score"] = heuristic_quality(skill_data)

        return skill_data

    @staticmethod
    def _assemble_content(skill_data: dict[str, Any]) -> str:
        parts: list[str] = []
        if skill_data.get("when_to_use"):
            parts.extend(["## When to Use", skill_data["when_to_use"], ""])
        if skill_data.get("procedure"):
            parts.extend(["## Procedure", skill_data["procedure"], ""])
        if skill_data.get("pitfalls"):
            parts.extend(["## Pitfalls", skill_data["pitfalls"], ""])
        if skill_data.get("verification"):
            parts.extend(["## Verification", skill_data["verification"], ""])
        return "\n".join(parts).strip()
