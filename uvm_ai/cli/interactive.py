"""Interactive session mode for UVM-AI."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

from uvm_ai.codegen.emitter import TemplateEmitter
from uvm_ai.codegen.project import ProjectManager
from uvm_ai.comms.dialogue import DialogueManager
from uvm_ai.comms.message_bus import MessageBus
from uvm_ai.config.settings import Settings
from uvm_ai.models.dut_spec import DUTSpec

logger = logging.getLogger(__name__)


class InteractiveSession:
    """Interactive session for step-by-step testbench generation."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.bus = MessageBus()
        self.dialogue_mgr = DialogueManager(max_revisions=settings.max_revision_rounds)
        self.emitter = TemplateEmitter()
        self.project = ProjectManager(settings.output_dir)
        self._dut_spec: DUTSpec | None = None

    def load_spec(self, spec_path: str) -> DUTSpec:
        """Load a DUT spec from a JSON file."""
        with open(spec_path) as f:
            data = json.load(f)
        self._dut_spec = DUTSpec(**data)
        return self._dut_spec

    @property
    def dut_spec(self) -> DUTSpec | None:
        return self._dut_spec

    async def run(self) -> None:
        """Run the interactive session."""
        print("UVM-AI Interactive Session")
        print("=" * 40)
        print("Commands: load <file>, plan, generate, quit")
        print()

        while True:
            try:
                line = input("uvm-ai> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break

            if not line:
                continue

            parts = line.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""

            if cmd == "quit" or cmd == "exit":
                print("Goodbye!")
                break
            elif cmd == "load":
                if not arg:
                    print("Usage: load <spec_file.json>")
                    continue
                try:
                    spec = self.load_spec(arg)
                    print(f"Loaded DUT: {spec.name} ({len(spec.ports)} ports)")
                except Exception as e:
                    print(f"Error: {e}")
            elif cmd == "plan":
                if not self._dut_spec:
                    print("No DUT loaded. Use 'load <file>' first.")
                    continue
                self._show_plan()
            elif cmd == "generate":
                if not self._dut_spec:
                    print("No DUT loaded. Use 'load <file>' first.")
                    continue
                print("Generating testbench...")
                print("(Full generation requires API key configuration)")
            else:
                print(f"Unknown command: {cmd}")

    def _show_plan(self) -> None:
        if not self._dut_spec:
            return
        spec = self._dut_spec
        print(f"\nDUT: {spec.name}")
        print(f"Module: {spec.module_name}")
        print(f"Ports ({len(spec.ports)}):")
        for p in spec.ports:
            flags = []
            if p.is_clock:
                flags.append("CLK")
            if p.is_reset:
                flags.append("RST")
            flag_str = f" [{','.join(flags)}]" if flags else ""
            print(f"  {p.direction.value:6s} {p.sv_type:20s} {p.name}{flag_str}")
        if spec.protocols:
            print(f"Protocols ({len(spec.protocols)}):")
            for proto in spec.protocols:
                print(f"  {proto.name}: {proto.protocol_type}")
        print()
