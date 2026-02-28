"""Orchestrator agent — top-level controller for UVM testbench generation."""

from __future__ import annotations

import json
import logging
from typing import Any

from verifai.agents.base import BaseAgent
from verifai.codegen.emitter import TemplateEmitter
from verifai.codegen.project import ProjectManager
from verifai.comms.dialogue import DialogueManager
from verifai.comms.message_bus import MessageBus
from verifai.config.settings import AgentConfig
from verifai.models.dut_spec import DUTSpec
from verifai.models.messages import (
    AgentMessage,
    CodeArtifact,
    CoverageDirective,
    CoverageReport,
    PlanRequest,
    PlanResponse,
    ReviewFeedback,
    SequenceProposal,
)
from verifai.models.tb_plan import TestbenchPlan

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> dict[str, Any]:
    """Parse JSON from LLM text, stripping markdown code fences if present."""
    text = text.strip()
    if text.startswith("```"):
        first_nl = text.find("\n")
        text = text[first_nl + 1:] if first_nl != -1 else text[3:]
        last_fence = text.rfind("```")
        if last_fence != -1:
            text = text[:last_fence].rstrip()
    return json.loads(text)


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
        base_url: str = "",
        auth_token: str = "",
    ) -> None:
        super().__init__("orchestrator", config, bus, api_key, base_url, auth_token)
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
            plan_data = _extract_json(response)
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
            review_data = _extract_json(review_text)
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

    async def generate_components(self, dut_spec: "DUTSpec", plan: "TestbenchPlan") -> None:
        """Render all UVM components from the plan into project files using templates."""
        from verifai.models.uvm_component import (
            TransactionFieldSpec,
            UVMAgentSpec,
            UVMDriverSpec,
            UVMEnvSpec,
            UVMMonitorSpec,
            UVMScoreboardSpec,
            UVMSequenceItemSpec,
            UVMSequenceSpec,
            UVMSequencerSpec,
            UVMTestSpec,
        )
        from verifai.models.tb_plan import AgentPlan, SequencePlan

        prefix = plan.dut_name
        package_name = f"{prefix}_pkg"
        signal_ports = dut_spec.signal_ports

        # If the LLM gave us no agents, synthesise one from the DUT protocols
        agents = list(plan.agents)
        if not agents:
            logger.warning("Plan has no agents; synthesising default agent from DUT spec")
            default_proto = dut_spec.protocols[0] if dut_spec.protocols else None
            agents = [
                AgentPlan(
                    name=prefix,
                    interface_name=default_proto.name if default_proto else f"{prefix}_if",
                    protocol_type=default_proto.protocol_type if default_proto else "custom",
                    is_active=True,
                    has_scoreboard=True,
                )
            ]

        seq_item_files: list[str] = []
        sequence_files: list[str] = []
        agent_files: list[str] = []
        scoreboard_files: list[str] = []
        env_files: list[str] = []
        test_files: list[str] = []
        agent_specs: list[UVMAgentSpec] = []
        scoreboard_specs: list[UVMScoreboardSpec] = []

        for agent_plan in agents:
            aname = agent_plan.name
            txn_type = f"{aname}_seq_item"
            intf_name = agent_plan.interface_name or f"{aname}_if"

            # Sequence item: input ports are randomisable, outputs are not
            fields = [
                TransactionFieldSpec(
                    name=p.name,
                    sv_type="logic",
                    width=p.width,
                    is_rand=(p.direction.value == "input"),
                )
                for p in signal_ports
            ]
            seq_item = UVMSequenceItemSpec(
                name=txn_type, fields=fields, package_name=package_name
            )
            fname = f"{txn_type}.sv"
            self.project.add_file(fname, self.emitter.render(seq_item))
            seq_item_files.append(fname)

            # Driver
            driver = UVMDriverSpec(
                name=f"{aname}_driver",
                transaction_type=txn_type,
                interface_name=intf_name,
                package_name=package_name,
            )
            fname = f"{aname}_driver.sv"
            self.project.add_file(fname, self.emitter.render(driver))
            agent_files.append(fname)

            # Monitor
            monitor = UVMMonitorSpec(
                name=f"{aname}_monitor",
                transaction_type=txn_type,
                interface_name=intf_name,
                package_name=package_name,
            )
            fname = f"{aname}_monitor.sv"
            self.project.add_file(fname, self.emitter.render(monitor))
            agent_files.append(fname)

            # Sequencer
            sequencer = UVMSequencerSpec(
                name=f"{aname}_sequencer",
                transaction_type=txn_type,
                package_name=package_name,
            )
            fname = f"{aname}_sequencer.sv"
            self.project.add_file(fname, self.emitter.render(sequencer))
            agent_files.append(fname)

            # Agent
            agent_spec = UVMAgentSpec(
                name=f"{aname}_agent",
                is_active=agent_plan.is_active,
                transaction_type=txn_type,
                interface_name=intf_name,
                driver=driver if agent_plan.is_active else None,
                monitor=monitor,
                sequencer=sequencer if agent_plan.is_active else None,
                package_name=package_name,
            )
            fname = f"{aname}_agent.sv"
            self.project.add_file(fname, self.emitter.render(agent_spec))
            agent_files.append(fname)
            agent_specs.append(agent_spec)

            # Sequences — fall back to a single basic sequence if LLM gave none
            seqs = list(agent_plan.sequences)
            if not seqs:
                seqs = [SequencePlan(name=f"{aname}_basic_seq", description="Basic stimulus")]
            for seq_plan in seqs:
                seq_spec = UVMSequenceSpec(
                    name=seq_plan.name,
                    transaction_type=txn_type,
                    scenario_description=seq_plan.description,
                    package_name=package_name,
                )
                fname = f"sequences/{seq_plan.name}.sv"
                self.project.add_file(fname, self.emitter.render(seq_spec))
                sequence_files.append(fname)

            # Scoreboard
            if agent_plan.has_scoreboard:
                sb = UVMScoreboardSpec(
                    name=f"{aname}_scoreboard",
                    transaction_type=txn_type,
                    package_name=package_name,
                )
                fname = f"{aname}_scoreboard.sv"
                self.project.add_file(fname, self.emitter.render(sb))
                scoreboard_files.append(fname)
                scoreboard_specs.append(sb)

        # Environment
        env_spec = UVMEnvSpec(
            name=f"{prefix}_env",
            agents=agent_specs,
            scoreboards=scoreboard_specs,
            package_name=package_name,
        )
        fname = f"{prefix}_env.sv"
        self.project.add_file(fname, self.emitter.render(env_spec))
        env_files.append(fname)

        # Test
        test_spec = UVMTestSpec(
            name=f"{prefix}_base_test",
            env_type=env_spec.name,
            timeout_ns=plan.simulation_timeout_ns,
            package_name=package_name,
        )
        fname = f"{prefix}_base_test.sv"
        self.project.add_file(fname, self.emitter.render(test_spec))
        test_files.append(fname)

        # Interfaces — one per protocol
        for proto in dut_spec.protocols:
            proto_port_names = set(proto.port_names)
            proto_signals = [
                {"name": p.name, "sv_type": p.sv_type, "direction": p.direction.value}
                for p in signal_ports
                if p.name in proto_port_names
            ]
            intf_code = self.emitter.render_interface(proto.name, proto_signals)
            self.project.add_file(f"{proto.name}.sv", intf_code)

        # Testbench top
        interfaces = [
            {"name": proto.name, "type": proto.name, "config_name": f"vif_{proto.name}"}
            for proto in dut_spec.protocols
        ]
        port_connections = []
        for proto in dut_spec.protocols:
            proto_port_names = set(proto.port_names)
            for p in dut_spec.signal_ports:
                if p.name in proto_port_names:
                    port_connections.append(
                        {"port": p.name, "net": f"{proto.name}_if.{p.name}"}
                    )
        top_code = self.emitter.render_top(
            top_module_name=plan.top_module_name,
            package_name=package_name,
            dut_module_name=dut_spec.module_name,
            reset_name=dut_spec.reset_name,
            reset_active_low=dut_spec.reset_active_low,
            clock_period_ns=plan.clock_period_ns,
            reset_duration_ns=plan.reset_duration_ns,
            simulation_timeout_ns=plan.simulation_timeout_ns,
            interfaces=interfaces,
            port_connections=port_connections,
            dut_parameters=[
                {"name": p.name, "value": p.default_value} for p in dut_spec.parameters
            ],
        )
        self.project.add_file(f"{plan.top_module_name}.sv", top_code)

        # Package
        pkg_code = self.emitter.render_package(
            package_name=package_name,
            sequence_items=seq_item_files,
            sequences=sequence_files,
            agent_files=agent_files,
            scoreboards=scoreboard_files,
            environments=env_files,
            tests=test_files,
        )
        self.project.add_file(f"{package_name}.sv", pkg_code)

        logger.info(
            "Generated %d component files for %s",
            len(self.project.registered_files),
            plan.name,
        )

    @property
    def plan(self) -> TestbenchPlan | None:
        return self._plan

    @property
    def artifacts(self) -> list[CodeArtifact]:
        return list(self._artifacts)
