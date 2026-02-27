"""Tests for verifai data models."""

import pytest

from verifai.models.dut_spec import DUTSpec, PortSpec, PortDirection, ParameterSpec, ProtocolSpec
from verifai.models.tb_plan import TestbenchPlan, AgentPlan, SequencePlan
from verifai.models.uvm_component import (
    UVMSequenceItemSpec,
    UVMDriverSpec,
    UVMMonitorSpec,
    UVMAgentSpec,
    UVMEnvSpec,
    UVMScoreboardSpec,
    TransactionFieldSpec,
    UVMComponentType,
)
from verifai.models.messages import (
    PlanRequest,
    PlanResponse,
    ReviewFeedback,
    InterfaceContract,
    CoverageReport,
    CoverageDirective,
    CodeArtifact,
)


class TestDUTSpec:
    def test_basic_creation(self):
        spec = DUTSpec(name="my_dut")
        assert spec.name == "my_dut"
        assert spec.module_name == "my_dut"

    def test_port_properties(self):
        spec = DUTSpec(
            name="test",
            ports=[
                PortSpec(name="clk", direction=PortDirection.INPUT, is_clock=True),
                PortSpec(name="rst_n", direction=PortDirection.INPUT, is_reset=True),
                PortSpec(name="data_in", direction=PortDirection.INPUT, width=8),
                PortSpec(name="data_out", direction=PortDirection.OUTPUT, width=8),
            ],
        )
        assert len(spec.input_ports) == 3
        assert len(spec.output_ports) == 1
        assert spec.clock_port is not None
        assert spec.clock_port.name == "clk"
        assert spec.reset_port is not None
        assert len(spec.signal_ports) == 2

    def test_port_sv_type(self):
        p1 = PortSpec(name="a", direction=PortDirection.INPUT, width=1)
        assert p1.sv_type == "logic"

        p8 = PortSpec(name="b", direction=PortDirection.INPUT, width=8)
        assert p8.sv_type == "logic [7:0]"


class TestTestbenchPlan:
    def test_basic_plan(self):
        plan = TestbenchPlan(name="my_tb", dut_name="my_dut")
        assert plan.top_module_name == "tb_my_dut_top"
        assert plan.coverage_target == 95.0

    def test_all_sequences(self):
        plan = TestbenchPlan(
            name="tb",
            dut_name="dut",
            agents=[
                AgentPlan(
                    name="agent1",
                    sequences=[
                        SequencePlan(name="seq1"),
                        SequencePlan(name="seq2"),
                    ],
                ),
                AgentPlan(
                    name="agent2",
                    sequences=[SequencePlan(name="seq3")],
                ),
            ],
        )
        assert len(plan.all_sequences) == 3


class TestUVMComponents:
    def test_sequence_item(self):
        item = UVMSequenceItemSpec(
            name="alu_item",
            fields=[
                TransactionFieldSpec(name="opcode", width=2, is_rand=True),
                TransactionFieldSpec(name="operand_a", width=8, is_rand=True),
                TransactionFieldSpec(name="result", width=8, is_rand=False),
            ],
        )
        assert item.component_type == UVMComponentType.SEQUENCE_ITEM
        assert len(item.rand_fields) == 2

    def test_transaction_field(self):
        f = TransactionFieldSpec(name="data", width=8, is_rand=True)
        assert f.full_sv_type == "logic [7:0]"
        assert f.rand_prefix == "rand "

        f2 = TransactionFieldSpec(name="flag", width=1, is_rand=False)
        assert f2.full_sv_type == "logic"
        assert f2.rand_prefix == ""

    def test_agent_spec(self):
        agent = UVMAgentSpec(
            name="alu_agent",
            is_active=True,
            driver=UVMDriverSpec(name="alu_driver", transaction_type="alu_item", interface_name="alu_if"),
            monitor=UVMMonitorSpec(name="alu_monitor", transaction_type="alu_item", interface_name="alu_if"),
        )
        assert agent.component_type == UVMComponentType.AGENT
        assert agent.driver is not None
        assert agent.monitor is not None


class TestMessages:
    def test_plan_request(self):
        msg = PlanRequest(
            sender="orchestrator",
            recipient="env_agent",
            component_name="test_env",
            instructions="Generate the environment",
        )
        assert msg.message_type == "PlanRequest"
        assert msg.id  # auto-generated

    def test_coverage_report(self):
        report = CoverageReport(
            sender="scoreboard",
            recipient="orchestrator",
            overall_coverage=73.5,
            coverage_bins={"op_add": 100.0, "op_sub": 80.0, "overflow": 0.0},
            uncovered_scenarios=["overflow"],
        )
        assert report.overall_coverage == 73.5
        assert len(report.coverage_bins) == 3

    def test_code_artifact(self):
        artifact = CodeArtifact(
            sender="env_agent",
            recipient="codegen",
            filename="alu_env.sv",
            content="class alu_env extends uvm_env;",
        )
        assert artifact.language == "systemverilog"
