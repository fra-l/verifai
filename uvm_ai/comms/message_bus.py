"""Async publish/subscribe message bus for inter-agent communication."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine

from uvm_ai.models.messages import AgentMessage

logger = logging.getLogger(__name__)

Subscriber = Callable[[AgentMessage], Coroutine[Any, Any, None]]


class MessageBus:
    """Async pub/sub message bus with typed channels.

    Agents subscribe to message types or specific channels, and
    the bus routes messages accordingly.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Subscriber]] = defaultdict(list)
        self._type_subscribers: dict[type, list[Subscriber]] = defaultdict(list)
        self._history: list[AgentMessage] = []
        self._lock = asyncio.Lock()

    def subscribe(self, channel: str, callback: Subscriber) -> None:
        """Subscribe to messages on a named channel."""
        self._subscribers[channel].append(callback)
        logger.debug("Subscriber added to channel '%s'", channel)

    def subscribe_type(self, msg_type: type, callback: Subscriber) -> None:
        """Subscribe to all messages of a specific type."""
        self._type_subscribers[msg_type].append(callback)
        logger.debug("Subscriber added for type '%s'", msg_type.__name__)

    def unsubscribe(self, channel: str, callback: Subscriber) -> None:
        """Remove a subscriber from a channel."""
        subs = self._subscribers.get(channel, [])
        if callback in subs:
            subs.remove(callback)

    async def publish(self, channel: str, message: AgentMessage) -> None:
        """Publish a message to a named channel."""
        async with self._lock:
            self._history.append(message)

        logger.debug(
            "Publishing %s on channel '%s': %s -> %s",
            message.message_type, channel, message.sender, message.recipient,
        )

        tasks: list[Coroutine[Any, Any, None]] = []

        for cb in self._subscribers.get(channel, []):
            tasks.append(cb(message))

        for msg_type, cbs in self._type_subscribers.items():
            if isinstance(message, msg_type):
                for cb in cbs:
                    tasks.append(cb(message))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def send(self, message: AgentMessage) -> None:
        """Send a message to its recipient's channel (channel = recipient name)."""
        await self.publish(message.recipient, message)

    @property
    def history(self) -> list[AgentMessage]:
        return list(self._history)

    def get_history_for(self, agent_name: str) -> list[AgentMessage]:
        """Get all messages sent to or from a specific agent."""
        return [
            m for m in self._history
            if m.sender == agent_name or m.recipient == agent_name
        ]

    def clear_history(self) -> None:
        self._history.clear()
