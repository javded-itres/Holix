from typing import AsyncGenerator, List, Dict, Any
from openai import AsyncOpenAI
import json

from config import settings
from core.prompt_builder import build_system_prompt, format_tools_description


class StreamingAgentLoop:
    """Streaming version of agent loop for real-time responses."""

    def __init__(self, agent):
        """Initialize the streaming agent loop.

        Args:
            agent: Parent agent instance
        """
        self.agent = agent
        self.client: AsyncOpenAI = agent.client
        self.model: str = agent.model

    async def run_conversation_stream(
        self,
        user_input: str,
        conversation_id: str = "default"
    ) -> AsyncGenerator[str, None]:
        """Run a conversation with streaming responses.

        Args:
            user_input: User's input message
            conversation_id: Conversation identifier

        Yields:
            Response chunks as they're generated
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
        full_response = ""

        while step_count < max_steps:
            step_count += 1

            # Prepare messages for API
            api_messages = [
                {"role": "system", "content": system_prompt}
            ] + messages[-20:]

            try:
                # Call LLM with streaming
                stream = await self.client.chat.completions.create(
                    model=self.model,
                    messages=api_messages,
                    tools=self.agent.tools.get_schemas(),
                    tool_choice="auto",
                    temperature=settings.temperature,
                    stream=True
                )

                # Collect chunks
                current_message = {"role": "assistant", "content": ""}
                tool_calls_dict = {}

                async for chunk in stream:
                    delta = chunk.choices[0].delta

                    # Content chunk
                    if delta.content:
                        current_message["content"] += delta.content
                        full_response += delta.content
                        yield f"data: {json.dumps({'type': 'content', 'content': delta.content})}\n\n"

                    # Tool calls
                    if delta.tool_calls:
                        for tool_call_chunk in delta.tool_calls:
                            idx = tool_call_chunk.index
                            if idx not in tool_calls_dict:
                                tool_calls_dict[idx] = {
                                    "id": "",
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""}
                                }

                            if tool_call_chunk.id:
                                tool_calls_dict[idx]["id"] = tool_call_chunk.id

                            if tool_call_chunk.function:
                                if tool_call_chunk.function.name:
                                    tool_calls_dict[idx]["function"]["name"] = tool_call_chunk.function.name
                                if tool_call_chunk.function.arguments:
                                    tool_calls_dict[idx]["function"]["arguments"] += tool_call_chunk.function.arguments

                # Check for finish
                if chunk.choices[0].finish_reason == "stop":
                    # No tool calls, final response
                    messages.append(current_message)

                    # Save to memory
                    await self.agent.memory.save_message(
                        conversation_id,
                        "assistant",
                        current_message["content"]
                    )

                    # Send completion signal
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    return

                elif chunk.choices[0].finish_reason == "tool_calls":
                    # Tool calls requested
                    tool_calls = list(tool_calls_dict.values())
                    current_message["tool_calls"] = tool_calls
                    messages.append(current_message)

                    # Execute tools
                    for tool_call in tool_calls:
                        # Create proper tool call object
                        class ToolCall:
                            def __init__(self, data):
                                self.id = data["id"]
                                self.type = data["type"]
                                self.function = type('obj', (object,), {
                                    'name': data["function"]["name"],
                                    'arguments': data["function"]["arguments"]
                                })()

                        tool_call_obj = ToolCall(tool_call)
                        tool_name = tool_call_obj.function.name

                        yield f"data: {json.dumps({'type': 'tool_call', 'tool': tool_name})}\n\n"

                        result = await self.agent.tools.execute(tool_call_obj)

                        yield f"data: {json.dumps({'type': 'tool_result', 'tool': tool_name, 'result': result[:200]})}\n\n"

                        # Add tool result to messages
                        tool_msg = {
                            "role": "tool",
                            "tool_call_id": tool_call_obj.id,
                            "content": result
                        }
                        messages.append(tool_msg)

                        # Save to memory
                        await self.agent.memory.save_message(
                            conversation_id,
                            "tool",
                            result,
                            metadata={"tool_name": tool_name}
                        )

                    # Continue loop to process tool results
                    continue

            except Exception as e:
                error_msg = f"Error: {str(e)}"
                yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
                return

        # Max steps reached
        timeout_msg = f"Agent reached maximum steps ({max_steps})"
        yield f"data: {json.dumps({'type': 'error', 'message': timeout_msg})}\n\n"
