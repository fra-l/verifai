"""Inter-agent message types for the verifai communication protocol."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class MessagePriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class AgentMessage(BaseModel):
    """Base class for all inter-agent messages."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sender: str
    recipient: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    priority: MessagePriority = MessagePriority.NORMAL
    correlation_id: Optional[str] = None  # links request/response pairs
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def message_type(self) -> str:
        return self.__class__.__name__


class PlanRequest(AgentMessage):
    """Orchestrator asks a sub-agent to generate a component or plan."""

    component_name: str
    spec: dict[str, Any] = Field(default_factory=dict)
    instructions: str = ""
    context: dict[str, Any] = Field(default_factory=dict)


class PlanResponse(AgentMessage):
    """Sub-agent responds with a proposed plan or generated code."""

    component_name: str
    proposed_code: str = ""
    proposed_plan: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    confidence: float = 1.0  # 0.0 - 1.0


class ReviewFeedback(AgentMessage):
    """Orchestrator provides review feedback to a sub-agent."""

    component_name: str
    approved: bool = False
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    revised_spec: dict[str, Any] = Field(default_factory=dict)


class InterfaceContract(AgentMessage):
    """UVM Agent Agent tells Sequence Agent about transaction fields/constraints."""

    interface_name: str
    transaction_type: str
    fields: list[dict[str, Any]] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    protocol_notes: str = ""


class SequenceProposal(AgentMessage):
    """Sequence Agent proposes a new sequence to the Orchestrator."""

    sequence_name: str
    target_scenario: str = ""
    sequence_code: str = ""
    expected_coverage_impact: list[str] = Field(default_factory=list)


class CoverageReport(AgentMessage):
    """Scoreboard Agent reports coverage status."""

    overall_coverage: float = 0.0  # percentage
    coverage_bins: dict[str, float] = Field(default_factory=dict)
    uncovered_scenarios: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class CoverageDirective(AgentMessage):
    """Orchestrator directs Sequence Agent to target specific coverage holes."""

    target_bins: list[str] = Field(default_factory=list)
    target_scenarios: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    priority_order: list[str] = Field(default_factory=list)


class CodeArtifact(AgentMessage):
    """Any agent emits a code artifact for the codegen engine."""

    filename: str
    content: str
    language: str = "systemverilog"
    component_type: str = ""
    overwrite: bool = True
