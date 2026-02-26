"""UVM Agent Agent — generates driver, monitor, sequencer, and agent wrapper."""

from __future__ import annotations

import json
import logging
from typing import Any

from uvm_ai.agents.base import BaseAgent
from uvm_ai.codegen.emitter import TemplateEmitter
from uvm_ai.models.messages import (
    AgentMessage,
    CodeArtifact,
    InterfaceContract,
    PlanRequest,
    PlanResponse,
    ReviewFeedback,
)
from uvm_ai.models.uvm_component import (
    UVMAgentSpec,
    UVMDriverSpec,
    UVMMonitorSpec,
    UVMSequenceItemSpec,
    UVMSequencerSpec,
    TransactionFieldSpec,
)

logger = logging.getLogger(__name__)


class UVMAgentAgent(BaseAgent):
    """Generates per-interface UVM agents: driver, monitor, sequencer, seq_item."""

    @property
    def system_prompt(self) -> str:
        return (
            "You are the UVM Agent Agent in a testbench generation system. "
            "For each DUT interface/protocol, you generate:\n"
            "- uvm_sequence_item with proper fields, constraints, and UVM macros\n"
            "- uvm_driver with drive logic\n"
            "- uvm_monitor with sampling logic\n"
            "- uvm_sequencer parameterized with the sequence item\n"
            "- uvm_agent wrapper connecting all components\n\n"
            "Use proper UVM factory registration, config_db access for virtual "
            "interfaces, and analysis ports. Generate clean SystemVerilog."
        )

    async def on_message(self, message: AgentMessage) -> None:
        if isinstance(message, PlanRequest):
            await self._handle_plan_request(message)
        elif isinstance(message, ReviewFeedback):
            await self._handle_review_feedback(message)

    async def _handle_plan_request(self, request: PlanRequest) -> None:
        """Generate agent components from a plan request."""
        spec = request.spec
        instructions = request.instructions

        prompt = (
            f"Generate a complete UVM agent for this interface.\n\n"
            f"Spec: {json.dumps(spec, indent=2)}\n"
            f"Instructions: {instructions}\n\n"
            f"Generate all components: sequence_item, driver, monitor, "
            f"sequencer, and agent wrapper."
        )
        code = await self.call_llm(prompt)

        # Publish interface contract for the sequence agent
        if "transaction_fields" in spec:
            contract = InterfaceContract(
                sender=self.name,
                recipient="sequence_agent",
                interface_name=spec.get("interface_name", request.component_name),
                transaction_type=spec.get("transaction_type", f"{request.component_name}_item"),
                fields=spec.get("transaction_fields", []),
                constraints=spec.get("constraints", []),
            )
            await self.send_message(contract)

        response = PlanResponse(
            sender=self.name,
            recipient=request.sender,
            correlation_id=request.id,
            component_name=request.component_name,
            proposed_code=code,
            notes=["Generated full agent hierarchy"],
        )
        await self.send_message(response)

    async def _handle_review_feedback(self, feedback: ReviewFeedback) -> None:
        if feedback.approved:
            logger.info("[%s] Component %s approved", self.name, feedback.component_name)
            return

        prompt = (
            f"Revise the UVM agent code. Issues:\n"
            f"{json.dumps(feedback.issues, indent=2)}\n"
            f"Suggestions:\n{json.dumps(feedback.suggestions, indent=2)}\n"
        )
        revised_code = await self.call_llm(prompt)

        response = PlanResponse(
            sender=self.name,
            recipient=feedback.sender,
            correlation_id=feedback.correlation_id,
            component_name=feedback.component_name,
            proposed_code=revised_code,
            notes=["Revised based on feedback"],
        )
        await self.send_message(response)

    def generate_from_spec(
        self,
        agent_spec: UVMAgentSpec,
        seq_item_spec: UVMSequenceItemSpec,
        emitter: TemplateEmitter,
    ) -> dict[str, str]:
        """Generate all agent files directly from specs using templates."""
        files: dict[str, str] = {}
        files[f"{seq_item_spec.name}.sv"] = emitter.render(seq_item_spec)
        if agent_spec.driver:
            files[f"{agent_spec.driver.name}.sv"] = emitter.render(agent_spec.driver)
        if agent_spec.monitor:
            files[f"{agent_spec.monitor.name}.sv"] = emitter.render(agent_spec.monitor)
        if agent_spec.sequencer:
            files[f"{agent_spec.sequencer.name}.sv"] = emitter.render(agent_spec.sequencer)
        files[f"{agent_spec.name}.sv"] = emitter.render(agent_spec)
        return files
