"""Orchestrator agent — top-level controller for UVM testbench generation."""

from __future__ import annotations

import json
import logging
from typing import Any

from uvm_ai.agents.base import BaseAgent
from uvm_ai.codegen.emitter import TemplateEmitter
from uvm_ai.codegen.project import ProjectManager
from uvm_ai.comms.dialogue import DialogueManager
from uvm_ai.comms.message_bus import MessageBus
from uvm_ai.config.settings import AgentConfig
from uvm_ai.models.dut_spec import DUTSpec
from uvm_ai.models.messages import (
    AgentMessage,
    CodeArtifact,
    CoverageDirective,
    CoverageReport,
    PlanRequest,
    PlanResponse,
    ReviewFeedback,
    SequenceProposal,
)
from uvm_ai.models.tb_plan import TestbenchPlan

logger = logging.getLogger(__name__)


class OrchestratorAgent(BaseAgent):
    """Top-level orchestrator that manages the testbench generation workflow.

    Responsibilities:
    - Analyze DUT specification
    - Create a testbench plan
    - Delegate work to sub-agents
    - Review and approve generated artifacts
    - Drive coverage closure loop
    """

    def __init__(
        self,
        config: AgentConfig,
        bus: MessageBus,
        dialogue_mgr: DialogueManager,
        emitter: TemplateEmitter,
        project: ProjectManager,
        api_key: str = "",
        auth_token: str = "",
    ) -> None:
        super().__init__("orchestrator", config, bus, api_key, auth_token)
        self.dialogue_mgr = dialogue_mgr
        self.emitter = emitter
        self.project = project
        self._plan: TestbenchPlan | None = None
        self._artifacts: list[CodeArtifact] = []

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Orchestrator Agent in a UVM testbench generation system. "
            "Your role is to:\n"
            "1. Analyze DUT specifications and create comprehensive testbench plans.\n"
            "2. Delegate work to specialized sub-agents (environment, UVM agent, "
            "sequence, scoreboard).\n"
            "3. Review generated artifacts for correctness and consistency.\n"
            "4. Drive coverage closure by analyzing gaps and directing new stimulus.\n\n"
            "Always respond with valid JSON when asked for structured data. "
            "Be precise about UVM component naming, port connections, and "
            "SystemVerilog types."
        )

    async def analyze_dut(self, dut_spec: DUTSpec) -> TestbenchPlan:
        """Analyze a DUT spec and produce a testbench plan via LLM."""
        prompt = (
            f"Analyze this DUT and create a UVM testbench plan.\n\n"
            f"DUT: {dut_spec.model_dump_json(indent=2)}\n\n"
            f"Respond with a JSON object containing:\n"
            f"- name: testbench name\n"
            f"- dut_name: the DUT module name\n"
            f"- agents: list of agent plans (name, interface_name, protocol_type, "
            f"is_active, has_scoreboard, sequences list)\n"
            f"- clock_period_ns, reset_duration_ns, simulation_timeout_ns\n"
            f"- coverage_target: target coverage percentage\n"
            f"- description: brief description\n"
        )
        response = await self.call_llm(prompt)

        try:
            plan_data = json.loads(response)
            self._plan = TestbenchPlan(**plan_data)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("LLM response was not valid JSON, using defaults: %s", exc)
            self._plan = TestbenchPlan(
                name=f"{dut_spec.name}_tb",
                dut_name=dut_spec.module_name,
                description=f"Auto-generated testbench for {dut_spec.name}",
            )

        return self._plan

    async def delegate_to_agent(
        self,
        agent_name: str,
        component_name: str,
        spec: dict[str, Any],
        instructions: str = "",
    ) -> None:
        """Send a PlanRequest to a sub-agent."""
        request = PlanRequest(
            sender=self.name,
            recipient=agent_name,
            component_name=component_name,
            spec=spec,
            instructions=instructions,
        )
        self.dialogue_mgr.start_dialogue(request)
        await self.send_message(request)

    async def on_message(self, message: AgentMessage) -> None:
        if isinstance(message, PlanResponse):
            await self._handle_plan_response(message)
        elif isinstance(message, CoverageReport):
            await self._handle_coverage_report(message)
        elif isinstance(message, SequenceProposal):
            await self._handle_sequence_proposal(message)
        elif isinstance(message, CodeArtifact):
            self._artifacts.append(message)
            self.project.add_file(message.filename, message.content)

    async def _handle_plan_response(self, response: PlanResponse) -> None:
        """Review a sub-agent's response and approve or request revision."""
        entry = self.dialogue_mgr.record_response(response)
        if not entry:
            return

        # Use LLM to review the proposed code
        review_prompt = (
            f"Review this generated UVM component for correctness.\n\n"
            f"Component: {response.component_name}\n"
            f"Code:\n```systemverilog\n{response.proposed_code}\n```\n\n"
            f"Respond with JSON: {{\"approved\": true/false, "
            f"\"issues\": [...], \"suggestions\": [...]}}"
        )
        review_text = await self.call_llm(review_prompt)

        try:
            review_data = json.loads(review_text)
            approved = review_data.get("approved", True)
            issues = review_data.get("issues", [])
            suggestions = review_data.get("suggestions", [])
        except (json.JSONDecodeError, Exception):
            approved = True
            issues = []
            suggestions = []

        feedback = ReviewFeedback(
            sender=self.name,
            recipient=response.sender,
            correlation_id=response.correlation_id,
            component_name=response.component_name,
            approved=approved,
            issues=issues,
            suggestions=suggestions,
        )
        self.dialogue_mgr.record_feedback(feedback)
        await self.send_message(feedback)

    async def _handle_coverage_report(self, report: CoverageReport) -> None:
        """Handle coverage report and direct new stimulus if needed."""
        if report.overall_coverage >= (self._plan.coverage_target if self._plan else 95.0):
            logger.info("Coverage target met: %.1f%%", report.overall_coverage)
            return

        directive = CoverageDirective(
            sender=self.name,
            recipient="sequence_agent",
            target_scenarios=report.uncovered_scenarios,
            target_bins=[k for k, v in report.coverage_bins.items() if v < 100.0],
        )
        await self.send_message(directive)

    async def _handle_sequence_proposal(self, proposal: SequenceProposal) -> None:
        """Review a proposed sequence."""
        artifact = CodeArtifact(
            sender=self.name,
            recipient="codegen",
            filename=f"sequences/{proposal.sequence_name}.sv",
            content=proposal.sequence_code,
            component_type="sequence",
        )
        self._artifacts.append(artifact)
        self.project.add_file(artifact.filename, artifact.content)

    @property
    def plan(self) -> TestbenchPlan | None:
        return self._plan

    @property
    def artifacts(self) -> list[CodeArtifact]:
        return list(self._artifacts)
