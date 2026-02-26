"""Environment assembly agent — generates UVM env, interface, and top-level code."""

from __future__ import annotations

import json
import logging
from typing import Any

from uvm_ai.agents.base import BaseAgent
from uvm_ai.codegen.emitter import TemplateEmitter
from uvm_ai.models.messages import (
    AgentMessage,
    CodeArtifact,
    PlanRequest,
    PlanResponse,
    ReviewFeedback,
)
from uvm_ai.models.uvm_component import UVMEnvSpec, UVMAgentSpec, UVMScoreboardSpec

logger = logging.getLogger(__name__)


class EnvAgent(BaseAgent):
    """Generates the UVM environment, interfaces, and top-level module."""

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Environment Agent in a UVM testbench generation system. "
            "Your role is to generate UVM environment code including:\n"
            "- uvm_env class with proper agent and scoreboard instantiation\n"
            "- SystemVerilog interfaces with clocking blocks\n"
            "- Testbench top module with DUT instantiation\n"
            "- UVM package with proper include order\n\n"
            "Generate clean, synthesizable SystemVerilog. "
            "Follow UVM coding conventions strictly."
        )

    async def on_message(self, message: AgentMessage) -> None:
        if isinstance(message, PlanRequest):
            await self._handle_plan_request(message)
        elif isinstance(message, ReviewFeedback):
            await self._handle_review_feedback(message)

    async def _handle_plan_request(self, request: PlanRequest) -> None:
        """Generate environment code from a plan request."""
        spec = request.spec
        instructions = request.instructions

        prompt = (
            f"Generate a UVM environment for this testbench.\n\n"
            f"Spec: {json.dumps(spec, indent=2)}\n"
            f"Instructions: {instructions}\n\n"
            f"Generate the environment class code in SystemVerilog."
        )
        code = await self.call_llm(prompt)

        response = PlanResponse(
            sender=self.name,
            recipient=request.sender,
            correlation_id=request.id,
            component_name=request.component_name,
            proposed_code=code,
            notes=["Generated environment skeleton"],
        )
        await self.send_message(response)

    async def _handle_review_feedback(self, feedback: ReviewFeedback) -> None:
        """Handle revision requests."""
        if feedback.approved:
            logger.info("[%s] Component %s approved", self.name, feedback.component_name)
            return

        prompt = (
            f"Revise the UVM environment code. Issues found:\n"
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

    def generate_env_from_spec(self, env_spec: UVMEnvSpec, emitter: TemplateEmitter) -> str:
        """Generate environment code directly from a spec using templates."""
        return emitter.render(env_spec)
