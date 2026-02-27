"""Structured dialogue manager for request/response tracking between agents."""

from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from verifai.models.messages import (
    AgentMessage,
    PlanRequest,
    PlanResponse,
    ReviewFeedback,
)

logger = logging.getLogger(__name__)


class DialogueState(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    AWAITING_REVIEW = "awaiting_review"
    REVISION_REQUESTED = "revision_requested"
    APPROVED = "approved"
    FAILED = "failed"


class DialogueEntry(BaseModel):
    """Tracks a single request/response dialogue."""

    correlation_id: str
    requester: str
    responder: str
    state: DialogueState = DialogueState.PENDING
    request: Optional[PlanRequest] = None
    response: Optional[PlanResponse] = None
    feedback: Optional[ReviewFeedback] = None
    revision_count: int = 0
    max_revisions: int = 3


class DialogueManager:
    """Manages structured dialogues between agents.

    Tracks request/response pairs, review cycles, and ensures
    conversations reach resolution.
    """

    def __init__(self, max_revisions: int = 3) -> None:
        self._dialogues: dict[str, DialogueEntry] = {}
        self._max_revisions = max_revisions

    def start_dialogue(self, request: PlanRequest) -> DialogueEntry:
        """Register a new dialogue from a PlanRequest."""
        entry = DialogueEntry(
            correlation_id=request.id,
            requester=request.sender,
            responder=request.recipient,
            state=DialogueState.IN_PROGRESS,
            request=request,
            max_revisions=self._max_revisions,
        )
        self._dialogues[request.id] = entry
        logger.debug("Dialogue started: %s -> %s", request.sender, request.recipient)
        return entry

    def record_response(self, response: PlanResponse) -> Optional[DialogueEntry]:
        """Record a response and move dialogue to awaiting review."""
        cid = response.correlation_id
        if not cid or cid not in self._dialogues:
            logger.warning("No dialogue found for correlation_id=%s", cid)
            return None

        entry = self._dialogues[cid]
        entry.response = response
        entry.state = DialogueState.AWAITING_REVIEW
        logger.debug("Response recorded for dialogue %s", cid)
        return entry

    def record_feedback(self, feedback: ReviewFeedback) -> Optional[DialogueEntry]:
        """Record review feedback, moving to approved or revision_requested."""
        cid = feedback.correlation_id
        if not cid or cid not in self._dialogues:
            logger.warning("No dialogue found for correlation_id=%s", cid)
            return None

        entry = self._dialogues[cid]
        entry.feedback = feedback

        if feedback.approved:
            entry.state = DialogueState.APPROVED
            logger.debug("Dialogue %s approved", cid)
        else:
            entry.revision_count += 1
            if entry.revision_count >= entry.max_revisions:
                entry.state = DialogueState.FAILED
                logger.warning("Dialogue %s failed after %d revisions", cid, entry.revision_count)
            else:
                entry.state = DialogueState.REVISION_REQUESTED
                logger.debug("Revision %d requested for dialogue %s", entry.revision_count, cid)

        return entry

    def get_dialogue(self, correlation_id: str) -> Optional[DialogueEntry]:
        return self._dialogues.get(correlation_id)

    def get_active_dialogues(self) -> list[DialogueEntry]:
        """Return all dialogues that are not yet resolved."""
        return [
            d for d in self._dialogues.values()
            if d.state not in (DialogueState.APPROVED, DialogueState.FAILED)
        ]

    def get_dialogues_for_agent(self, agent_name: str) -> list[DialogueEntry]:
        return [
            d for d in self._dialogues.values()
            if d.requester == agent_name or d.responder == agent_name
        ]

    @property
    def all_dialogues(self) -> list[DialogueEntry]:
        return list(self._dialogues.values())
