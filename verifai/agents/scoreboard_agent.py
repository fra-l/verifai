"""Scoreboard/Coverage Agent — tracks coverage and suggests improvements."""

from __future__ import annotations

import json
import logging

from verifai.agents.base import BaseAgent
from verifai.codegen.emitter import TemplateEmitter
from verifai.models.messages import (
    AgentMessage,
    CodeArtifact,
    CoverageReport,
    PlanRequest,
    PlanResponse,
    ReviewFeedback,
)
from verifai.models.uvm_component import UVMScoreboardSpec

logger = logging.getLogger(__name__)


class ScoreboardAgent(BaseAgent):
    """Generates UVM scoreboards and coverage models, analyzes coverage reports."""

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Scoreboard/Coverage Agent in a UVM testbench generation system. "
            "Your role is to:\n"
            "- Generate UVM scoreboard classes with proper checking logic\n"
            "- Create functional coverage models (covergroups, coverpoints, crosses)\n"
            "- Analyze simulation coverage reports and identify gaps\n"
            "- Suggest sequences/scenarios to improve coverage\n\n"
            "Use uvm_analysis_imp for receiving transactions. "
            "Create thorough coverage models. Generate clean SystemVerilog."
        )

    async def on_message(self, message: AgentMessage) -> None:
        if isinstance(message, PlanRequest):
            await self._handle_plan_request(message)
        elif isinstance(message, ReviewFeedback):
            await self._handle_review_feedback(message)

    async def _handle_plan_request(self, request: PlanRequest) -> None:
        prompt = (
            f"Generate a UVM scoreboard and coverage model.\n\n"
            f"Spec: {json.dumps(request.spec, indent=2)}\n"
            f"Instructions: {request.instructions}\n\n"
            f"Include:\n"
            f"1. Scoreboard with comparison logic\n"
            f"2. Functional covergroup with relevant coverpoints\n"
        )
        code = await self.call_llm(prompt)

        response = PlanResponse(
            sender=self.name,
            recipient=request.sender,
            correlation_id=request.id,
            component_name=request.component_name,
            proposed_code=code,
            notes=["Generated scoreboard and coverage model"],
        )
        await self.send_message(response)

    async def _handle_review_feedback(self, feedback: ReviewFeedback) -> None:
        if feedback.approved:
            return

        prompt = (
            f"Revise the scoreboard/coverage code. Issues:\n"
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

    async def analyze_coverage(
        self,
        coverage_data: dict[str, float],
        target: float = 95.0,
    ) -> CoverageReport:
        """Analyze coverage data and produce a report with suggestions."""
        total = sum(coverage_data.values()) / max(len(coverage_data), 1)
        uncovered = [k for k, v in coverage_data.items() if v < 100.0]

        prompt = (
            f"Analyze this coverage report and suggest improvements.\n\n"
            f"Overall: {total:.1f}%\nTarget: {target}%\n"
            f"Coverage bins: {json.dumps(coverage_data, indent=2)}\n"
            f"Uncovered: {uncovered}\n\n"
            f"Suggest specific scenarios to improve coverage."
        )
        analysis = await self.call_llm(prompt)

        # Parse suggestions from LLM response
        suggestions = [line.strip("- ") for line in analysis.split("\n") if line.strip().startswith("-")]

        report = CoverageReport(
            sender=self.name,
            recipient="orchestrator",
            overall_coverage=total,
            coverage_bins=coverage_data,
            uncovered_scenarios=uncovered,
            suggestions=suggestions[:10],
        )
        return report

    def generate_from_spec(self, sb_spec: UVMScoreboardSpec, emitter: TemplateEmitter) -> str:
        """Generate scoreboard code directly from a spec using templates."""
        return emitter.render(sb_spec)
