"""Communication layer for inter-agent messaging."""

from uvm_ai.comms.message_bus import MessageBus
from uvm_ai.comms.dialogue import DialogueManager, DialogueState

__all__ = ["MessageBus", "DialogueManager", "DialogueState"]
