"""Communication layer for inter-agent messaging."""

from verifai.comms.message_bus import MessageBus
from verifai.comms.dialogue import DialogueManager, DialogueState

__all__ = ["MessageBus", "DialogueManager", "DialogueState"]
