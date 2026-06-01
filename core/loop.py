from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI

from config import settings
from core.prompt_builder import build_system_prompt, format_tools_description


class AgentLoop:
    """Main agent loop for processing user requests."""

    def __init__(self, agent):
        """Initialize the agent loop.

        Args:
            agent: Parent agent instance
        """
        self.agent = agent
        self.client: AsyncOpenAI = agent.client
        self.model: str = agent.model

    async def run_conversation(
        self,
        user_input: str,
        conversation_id: str = "default"
    ) -> str:
        """Run a conversation with the agent.

        Args:
            user_input: User's input message
            conversation_id: Conversation identifier

        Returns:
            Agent's response
        """
        # Load conversation history
        messages = await self.agent.memory.get_conversation(conversation_id)

        # Add user message
        user_message = {"role": "user", "content": user_input}
        messages.append(user_message)
        await self.agent.memory.save_message(
            conversation_id,
            "user",
            user_input
        )

        # Get relevant skills
        relevant_skills = self.agent.skills.get_relevant_skills(user_input, top_k=3)
        skills_formatted = self.agent.skills.format_skills_for_prompt(relevant_skills)

        # Build system prompt
        tools_desc = format_tools_description(self.agent.tools.get_schemas())
        system_prompt = build_system_prompt(
            tools_description=tools_desc,
            active_skills=relevant_skills,
            skills_formatted=skills_formatted
        )

        # Agent loop
        step_count = 0
        max_steps = settings.max_steps

        while step_count < max_steps:
            step_count += 1

            # Prepare messages for API (include system prompt)
            api_messages = [
                {"role": "system", "content": system_prompt}
            ] + messages[-20:]  # Keep last 20 messages for context

            # Call LLM
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=api_messages,
                    tools=self.agent.tools.get_schemas(),
                    tool_choice="auto",
                    temperature=settings.temperature
                )
            except Exception as e:
                error_msg = f"Error calling LLM: {str(e)}"
                await self.agent.memory.save_message(
                    conversation_id,
                    "assistant",
                    error_msg
                )
                return error_msg

            message = response.choices[0].message

            # Convert message to dict for storage
            msg_dict = {
                "role": "assistant",
                "content": message.content or ""
            }

            # Check if there are tool calls
            if message.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in message.tool_calls
                ]

                messages.append(msg_dict)

                # Execute each tool call
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    print(f"\n[Tool Call] {tool_name}")

                    result = await self.agent.tools.execute(tool_call)
                    print(f"[Tool Result] {result[:200]}..." if len(result) > 200 else f"[Tool Result] {result}")

                    # Add tool result to messages
                    tool_msg = {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result
                    }
                    messages.append(tool_msg)

                    # Save tool result to memory
                    await self.agent.memory.save_message(
                        conversation_id,
                        "tool",
                        result,
                        metadata={"tool_name": tool_name}
                    )

                # Continue loop to process tool results
                continue

            else:
                # No tool calls, this is the final response
                final_response = message.content or "No response generated"

                messages.append(msg_dict)

                # Save assistant message
                await self.agent.memory.save_message(
                    conversation_id,
                    "assistant",
                    final_response
                )

                # Self-improvement check
                await self.self_improve(conversation_id, messages, final_response)

                return final_response

        # Max steps reached
        timeout_msg = f"Agent reached maximum steps ({max_steps}). Task may be too complex."
        await self.agent.memory.save_message(
            conversation_id,
            "assistant",
            timeout_msg
        )
        return timeout_msg

    async def self_improve(
        self,
        conversation_id: str,
        messages: List[Dict[str, Any]],
        final_response: str
    ) -> None:
        """Analyze the conversation and potentially create a new skill.

        Args:
            conversation_id: Conversation ID
            messages: All conversation messages
            final_response: Final agent response
        """
        try:
            # Check if we should create a skill
            should_create = await self.agent.skills.should_create_skill(
                messages,
                final_response
            )

            if should_create:
                print("\n[Self-Improvement] Analyzing session for skill creation...")

                # Get the original user query
                user_messages = [m for m in messages if m.get("role") == "user"]
                if not user_messages:
                    return

                task_description = user_messages[0].get("content", "")

                # Generate skill
                from core.skills.generator import SkillGenerator
                generator = SkillGenerator(self.client)

                skill_data = await generator.create_skill_from_session(
                    messages,
                    task_description
                )

                # Save the skill
                if skill_data and skill_data.get("name"):
                    filepath = self.agent.skills.save_skill(
                        name=skill_data["name"],
                        description=skill_data["description"],
                        content=skill_data["content"],
                        tags=skill_data.get("tags", []),
                        examples=skill_data.get("examples", [])
                    )

                    print(f"[Self-Improvement] Created new skill: {skill_data['name']}")
                    print(f"[Self-Improvement] Saved to: {filepath}")

        except Exception as e:
            print(f"[Self-Improvement] Error during self-improvement: {e}")
            # Don't fail the whole conversation if skill creation fails
            pass
