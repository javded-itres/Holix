#!/usr/bin/env python3
"""
Helix CLI - Command-line interface for the Helix agent.
"""

import asyncio
import sys
from pathlib import Path

from core.agent import HelixAgent


async def interactive_mode():
    """Run the agent in interactive mode."""
    print("=" * 60)
    print("HELIX - Self-Improving AI Agent")
    print("=" * 60)
    print()

    # Initialize agent
    agent = HelixAgent()
    await agent.initialize()

    print("Type 'exit' or 'quit' to exit")
    print("Type 'history' to see conversation history")
    print("Type 'skills' to list available skills")
    print("Type 'tools' to list available tools")
    print()

    conversation_id = "cli_session"

    while True:
        try:
            # Get user input
            user_input = input("\n\033[1;32mYou:\033[0m ")

            if not user_input.strip():
                continue

            # Handle special commands
            if user_input.lower() in ["exit", "quit"]:
                print("\nGoodbye!")
                break

            elif user_input.lower() == "history":
                history = await agent.get_conversation_history(conversation_id, limit=10)
                print("\n\033[1;36m=== Recent History ===\033[0m")
                for msg in history:
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")
                    print(f"\n{role.upper()}: {content[:200]}...")
                continue

            elif user_input.lower() == "skills":
                skills = agent.get_skills()
                print(f"\n\033[1;36m=== Available Skills ({len(skills)}) ===\033[0m")
                for name, skill in skills.items():
                    desc = skill.get("description", "No description")
                    print(f"\n- {name}: {desc}")
                continue

            elif user_input.lower() == "tools":
                tools = agent.get_tools()
                print(f"\n\033[1;36m=== Available Tools ({len(tools)}) ===\033[0m")
                for tool in tools:
                    print(f"- {tool}")
                continue

            # Run agent
            print("\n\033[1;34mHelix:\033[0m ", end="", flush=True)

            response = await agent.run(user_input, conversation_id)

            print(response)

        except KeyboardInterrupt:
            print("\n\nInterrupted. Type 'exit' to quit.")
            continue

        except Exception as e:
            print(f"\n\033[1;31mError: {e}\033[0m")
            continue


async def one_shot_mode(query: str):
    """Run a single query and exit."""
    agent = HelixAgent()
    await agent.initialize()

    response = await agent.run(query, "oneshot")
    print(response)


async def main():
    """Main CLI entry point."""
    if len(sys.argv) > 1:
        # One-shot mode with command-line argument
        query = " ".join(sys.argv[1:])
        await one_shot_mode(query)
    else:
        # Interactive mode
        await interactive_mode()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nExiting...")
        sys.exit(0)
