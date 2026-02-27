"""Template renderer for SystemVerilog/UVM code generation using Jinja2."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from verifai.models.uvm_component import (
    UVMAgentSpec,
    UVMComponentSpec,
    UVMDriverSpec,
    UVMEnvSpec,
    UVMMonitorSpec,
    UVMScoreboardSpec,
    UVMSequenceItemSpec,
    UVMSequenceSpec,
    UVMSequencerSpec,
    UVMTestSpec,
)

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# Map component types to template file names
_TEMPLATE_MAP: dict[type, str] = {
    UVMSequenceItemSpec: "sequence_item.sv.j2",
    UVMDriverSpec: "driver.sv.j2",
    UVMMonitorSpec: "monitor.sv.j2",
    UVMSequencerSpec: "sequencer.sv.j2",
    UVMSequenceSpec: "sequence.sv.j2",
    UVMAgentSpec: "agent.sv.j2",
    UVMScoreboardSpec: "scoreboard.sv.j2",
    UVMEnvSpec: "env.sv.j2",
    UVMTestSpec: "test.sv.j2",
}


class TemplateEmitter:
    """Renders UVM component specifications into SystemVerilog using Jinja2 templates."""

    def __init__(self, templates_dir: Path | None = None) -> None:
        tdir = templates_dir or TEMPLATES_DIR
        self._env = Environment(
            loader=FileSystemLoader(str(tdir)),
            autoescape=select_autoescape([]),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

    def render(self, spec: UVMComponentSpec, **extra_context: Any) -> str:
        """Render a UVM component spec to SystemVerilog code."""
        template_name = _TEMPLATE_MAP.get(type(spec))
        if not template_name:
            raise ValueError(f"No template registered for {type(spec).__name__}")

        template = self._env.get_template(template_name)
        context = spec.model_dump()
        context.update(extra_context)
        context["spec"] = spec

        result = template.render(**context)
        logger.debug("Rendered %s -> %s", spec.name, template_name)
        return result

    def render_interface(self, name: str, signals: list[dict[str, Any]]) -> str:
        """Render a SystemVerilog interface."""
        template = self._env.get_template("interface.sv.j2")
        return template.render(name=name, signals=signals)

    def render_top(self, **context: Any) -> str:
        """Render the testbench top module."""
        template = self._env.get_template("tb_top.sv.j2")
        return template.render(**context)

    def render_package(self, **context: Any) -> str:
        """Render a UVM package file."""
        template = self._env.get_template("package.sv.j2")
        return template.render(**context)

    def has_template(self, spec_type: type) -> bool:
        return spec_type in _TEMPLATE_MAP
