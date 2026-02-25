import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock

async def main():
    # Simple query
    async for message in query(prompt="Hello Claude"):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(block.text)

    # With options
    options = ClaudeAgentOptions(
        system_prompt="You are a helpful assistant",
        max_turns=1
    )

    async for message in query(prompt="Tell me a joke", options=options):
        print(message)

asyncio.run(main())