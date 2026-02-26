"""Tests for the code generation engine."""

import tempfile
from pathlib import Path

import pytest

from uvm_ai.codegen.emitter import TemplateEmitter
from uvm_ai.codegen.project import ProjectManager
from uvm_ai.models.uvm_component import (
    TransactionFieldSpec,
    UVMAgentSpec,
    UVMDriverSpec,
    UVMEnvSpec,
    UVMMonitorSpec,
    UVMScoreboardSpec,
    UVMSequenceItemSpec,
    UVMSequenceSpec,
    UVMSequencerSpec,
)


@pytest.fixture
def emitter():
    return TemplateEmitter()


class TestTemplateEmitter:
    def test_render_sequence_item(self, emitter):
        spec = UVMSequenceItemSpec(
            name="alu_item",
            fields=[
                TransactionFieldSpec(name="opcode", width=2, is_rand=True),
                TransactionFieldSpec(name="operand_a", width=8, is_rand=True),
                TransactionFieldSpec(name="result", width=8, is_rand=False),
            ],
        )
        code = emitter.render(spec)
        assert "class alu_item" in code
        assert "rand" in code
        assert "opcode" in code
        assert "`uvm_object_utils_begin" in code

    def test_render_driver(self, emitter):
        spec = UVMDriverSpec(
            name="alu_driver",
            transaction_type="alu_item",
            interface_name="alu_if",
        )
        code = emitter.render(spec)
        assert "class alu_driver" in code
        assert "uvm_driver" in code
        assert "alu_if" in code
        assert "drive_item" in code

    def test_render_monitor(self, emitter):
        spec = UVMMonitorSpec(
            name="alu_monitor",
            transaction_type="alu_item",
            interface_name="alu_if",
        )
        code = emitter.render(spec)
        assert "class alu_monitor" in code
        assert "analysis_port" in code

    def test_render_sequence(self, emitter):
        spec = UVMSequenceSpec(
            name="alu_base_seq",
            transaction_type="alu_item",
            num_items=20,
        )
        code = emitter.render(spec)
        assert "class alu_base_seq" in code
        assert "20" in code
        assert "body" in code

    def test_render_scoreboard(self, emitter):
        spec = UVMScoreboardSpec(
            name="alu_scoreboard",
            transaction_type="alu_item",
        )
        code = emitter.render(spec)
        assert "class alu_scoreboard" in code
        assert "analysis_imp" in code

    def test_render_agent(self, emitter):
        spec = UVMAgentSpec(
            name="alu_agent",
            is_active=True,
            driver=UVMDriverSpec(name="alu_driver", transaction_type="alu_item", interface_name="alu_if"),
            monitor=UVMMonitorSpec(name="alu_monitor", transaction_type="alu_item", interface_name="alu_if"),
            sequencer=UVMSequencerSpec(name="alu_sequencer", transaction_type="alu_item"),
        )
        code = emitter.render(spec)
        assert "class alu_agent" in code
        assert "alu_driver" in code
        assert "alu_monitor" in code
        assert "alu_sequencer" in code

    def test_render_env(self, emitter):
        agent = UVMAgentSpec(name="alu_agent")
        sb = UVMScoreboardSpec(name="alu_sb", transaction_type="alu_item")
        spec = UVMEnvSpec(
            name="alu_env",
            agents=[agent],
            scoreboards=[sb],
        )
        code = emitter.render(spec)
        assert "class alu_env" in code
        assert "alu_agent" in code
        assert "alu_sb" in code


class TestProjectManager:
    def test_add_and_write_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pm = ProjectManager(Path(tmpdir))
            pm.add_file("src/driver.sv", "// driver code")
            pm.add_file("src/monitor.sv", "// monitor code")

            written = pm.write_all()
            assert len(written) == 2
            assert (Path(tmpdir) / "src" / "driver.sv").exists()

    def test_generate_filelist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pm = ProjectManager(Path(tmpdir))
            pm.add_file("alu_pkg.sv", "package alu_pkg;")
            pm.add_file("alu_driver.sv", "class alu_driver;")
            pm.add_file("tb_top.sv", "module tb_top;")

            fl = pm.generate_filelist()
            assert "alu_pkg.sv" in fl
            assert "alu_driver.sv" in fl
            assert "tb_top.sv" in fl

    def test_generate_makefile(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pm = ProjectManager(Path(tmpdir))
            mk = pm.generate_makefile("xcelium")
            assert "xrun" in mk

            pm2 = ProjectManager(Path(tmpdir))
            mk2 = pm2.generate_makefile("vcs")
            assert "vcs" in mk2
