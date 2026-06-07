from typing import List, Dict, Any
from openai import AsyncOpenAI


class SkillGenerator:
    """Generates new skills from successful agent sessions."""

    def __init__(self, llm_client: AsyncOpenAI, *, model: str):
        self.client = llm_client
        self.model = (model or "").strip()
        if not self.model:
            raise ValueError("SkillGenerator requires an active agent model (profile default), not global settings.")

    async def create_skill_from_session(
        self,
        messages: List[Dict[str, Any]],
        task_description: str
    ) -> Dict[str, Any]:
        """Generate a new skill from a successful session.

        Args:
            messages: Conversation messages
            task_description: Description of the task that was solved

        Returns:
            Dictionary containing skill metadata and content
        """
        # Build conversation summary for the LLM
        conversation_summary = self._build_conversation_summary(messages)

        prompt = f"""You just successfully completed this task: {task_description}

Here's the conversation history:

{conversation_summary}

Based on this successful execution, create a reusable skill that can help solve similar tasks in the future.

Provide your response in this exact format:

SKILL_NAME: (a_snake_case_name_for_the_skill)
DESCRIPTION: (brief one-line description)
TAGS: (comma-separated tags, e.g., python, web, fastapi)

CONTENT:
(Markdown-formatted instructions and best practices for solving this type of task.
Include step-by-step approach, common pitfalls, and key considerations.)

EXAMPLES:
- (example use case 1)
- (example use case 2)
"""

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at analyzing successful task completions and creating reusable skills."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3
        )

        skill_text = response.choices[0].message.content

        # Parse the skill response
        skill_data = self._parse_skill_response(skill_text)

        return skill_data

    def _build_conversation_summary(
        self,
        messages: List[Dict[str, Any]]
    ) -> str:
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

    def _parse_skill_response(
        self,
        response: str
    ) -> Dict[str, Any]:
        """Parse the LLM's skill generation response.

        Args:
            response: Raw LLM response

        Returns:
            Parsed skill data
        """
        lines = response.strip().split('\n')

        skill_data = {
            "name": "unnamed_skill",
            "description": "",
            "tags": [],
            "content": "",
            "examples": []
        }

        current_section = None
        content_lines = []
        examples_lines = []

        for line in lines:
            if line.startswith("SKILL_NAME:"):
                skill_data["name"] = line.replace("SKILL_NAME:", "").strip()
            elif line.startswith("DESCRIPTION:"):
                skill_data["description"] = line.replace("DESCRIPTION:", "").strip()
            elif line.startswith("TAGS:"):
                tags_str = line.replace("TAGS:", "").strip()
                skill_data["tags"] = [t.strip() for t in tags_str.split(",") if t.strip()]
            elif line.startswith("CONTENT:"):
                current_section = "content"
            elif line.startswith("EXAMPLES:"):
                current_section = "examples"
            else:
                if current_section == "content":
                    content_lines.append(line)
                elif current_section == "examples":
                    if line.strip().startswith("-"):
                        examples_lines.append(line.strip()[1:].strip())

        skill_data["content"] = "\n".join(content_lines).strip()
        skill_data["examples"] = examples_lines

        return skill_data
