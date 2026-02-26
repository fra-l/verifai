"""Base class for all UVM-AI agents."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

import anthropic

from uvm_ai.comms.message_bus import MessageBus
from uvm_ai.config.settings import AgentConfig
from uvm_ai.models.messages import AgentMessage

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base class for AI agents in the UVM-AI system.

    Each agent wraps an Anthropic Claude API call with a specialized
    system prompt and handles messages via the MessageBus.
    """

    def __init__(
        self,
        name: str,
        config: AgentConfig,
        bus: MessageBus,
        api_key: str = "",
        auth_token: str = "",
    ) -> None:
        self.name = name
        self.config = config
        self.bus = bus
        self._client: anthropic.AsyncAnthropic | None = None
        self._api_key = api_key
        self._auth_token = auth_token
        self._conversation: list[dict[str, str]] = []

        # Subscribe to messages directed at this agent
        self.bus.subscribe(self.name, self._handle_message)

    @property
    def client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            if self._auth_token:
                self._client = anthropic.AsyncAnthropic(auth_token=self._auth_token)
            else:
                self._client = anthropic.AsyncAnthropic(api_key=self._api_key or None)
        return self._client

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Return the system prompt for this agent."""
        ...

    async def _handle_message(self, message: AgentMessage) -> None:
        """Handle an incoming message from the bus."""
        logger.info("[%s] Received %s from %s", self.name, message.message_type, message.sender)
        await self.on_message(message)

    @abstractmethod
    async def on_message(self, message: AgentMessage) -> None:
        """Process an incoming message. Subclasses must implement."""
        ...

    async def call_llm(self, user_prompt: str) -> str:
        """Make a call to the Claude API with the agent's system prompt."""
        self._conversation.append({"role": "user", "content": user_prompt})

        system = self.config.system_prompt_override or self.system_prompt
        response = await self.client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            system=system,
            messages=list(self._conversation),
        )

        assistant_text = response.content[0].text
        self._conversation.append({"role": "assistant", "content": assistant_text})

        logger.debug("[%s] LLM response length: %d chars", self.name, len(assistant_text))
        return assistant_text

    async def send_message(self, message: AgentMessage) -> None:
        """Send a message via the bus."""
        await self.bus.send(message)

    def reset_conversation(self) -> None:
        """Clear the conversation history for this agent."""
        self._conversation.clear()
