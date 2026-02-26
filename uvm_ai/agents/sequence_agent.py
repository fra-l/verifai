"""Sequence Agent — generates and refines stimulus sequences."""

from __future__ import annotations

import json
import logging

from uvm_ai.agents.base import BaseAgent
from uvm_ai.codegen.emitter import TemplateEmitter
from uvm_ai.models.messages import (
    AgentMessage,
    CoverageDirective,
    InterfaceContract,
    PlanRequest,
    PlanResponse,
    ReviewFeedback,
    SequenceProposal,
)
from uvm_ai.models.uvm_component import UVMSequenceSpec

logger = logging.getLogger(__name__)


class SequenceAgent(BaseAgent):
    """Generates UVM sequences and sequence items for stimulus generation.

    Can create targeted sequences in response to coverage directives.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._contracts: dict[str, InterfaceContract] = {}

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Sequence Agent in a UVM testbench generation system. "
            "Your role is to create UVM sequences that:\n"
            "- Exercise all DUT functionality through constrained-random stimulus\n"
            "- Target specific coverage goals when directed\n"
            "- Follow UVM sequence/sequence_item patterns properly\n"
            "- Use appropriate randomization constraints\n\n"
            "When given coverage directives, create focused sequences that target "
            "the specific uncovered scenarios. Generate clean SystemVerilog."
        )

    async def on_message(self, message: AgentMessage) -> None:
        if isinstance(message, PlanRequest):
            await self._handle_plan_request(message)
        elif isinstance(message, InterfaceContract):
            await self._handle_interface_contract(message)
        elif isinstance(message, CoverageDirective):
            await self._handle_coverage_directive(message)
        elif isinstance(message, ReviewFeedback):
            await self._handle_review_feedback(message)

    async def _handle_plan_request(self, request: PlanRequest) -> None:
        prompt = (
            f"Generate UVM sequences for this component.\n\n"
            f"Spec: {json.dumps(request.spec, indent=2)}\n"
            f"Instructions: {request.instructions}\n\n"
            f"Create base sequences with proper randomization."
        )
        code = await self.call_llm(prompt)

        response = PlanResponse(
            sender=self.name,
            recipient=request.sender,
            correlation_id=request.id,
            component_name=request.component_name,
            proposed_code=code,
            notes=["Generated base sequences"],
        )
        await self.send_message(response)

    async def _handle_interface_contract(self, contract: InterfaceContract) -> None:
        """Store interface contract for use in sequence generation."""
        self._contracts[contract.interface_name] = contract
        logger.info(
            "[%s] Received interface contract for %s (%d fields)",
            self.name, contract.interface_name, len(contract.fields),
        )

    async def _handle_coverage_directive(self, directive: CoverageDirective) -> None:
        """Generate targeted sequences to hit uncovered bins."""
        prompt = (
            f"Create targeted UVM sequences to cover these scenarios:\n"
            f"Target scenarios: {json.dumps(directive.target_scenarios)}\n"
            f"Target bins: {json.dumps(directive.target_bins)}\n"
            f"Constraints: {json.dumps(directive.constraints)}\n\n"
            f"Known interfaces: {list(self._contracts.keys())}\n"
            f"Generate focused sequences with tight constraints to hit these targets."
        )
        code = await self.call_llm(prompt)

        proposal = SequenceProposal(
            sender=self.name,
            recipient="orchestrator",
            sequence_name="targeted_coverage_seq",
            target_scenario=", ".join(directive.target_scenarios[:3]),
            sequence_code=code,
            expected_coverage_impact=directive.target_bins,
        )
        await self.send_message(proposal)

    async def _handle_review_feedback(self, feedback: ReviewFeedback) -> None:
        if feedback.approved:
            return

        prompt = (
            f"Revise sequence code. Issues:\n"
            f"{json.dumps(feedback.issues, indent=2)}\n"
        )
        revised_code = await self.call_llm(prompt)

        response = PlanResponse(
            sender=self.name,
            recipient=feedback.sender,
            correlation_id=feedback.correlation_id,
            component_name=feedback.component_name,
            proposed_code=revised_code,
        )
        await self.send_message(response)

    def generate_from_spec(self, seq_spec: UVMSequenceSpec, emitter: TemplateEmitter) -> str:
        """Generate sequence code directly from a spec using templates."""
        return emitter.render(seq_spec)
