"""Manages the output project file tree and build artifacts."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ProjectManager:
    """Manages the output directory tree for generated UVM testbench files."""

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir
        self._files: dict[str, str] = {}  # relative path -> content

    @property
    def output_dir(self) -> Path:
        return self._output_dir

    def add_file(self, relative_path: str, content: str) -> None:
        """Register a file to be written."""
        self._files[relative_path] = content
        logger.debug("Registered file: %s", relative_path)

    def write_all(self) -> list[Path]:
        """Write all registered files to disk."""
        written: list[Path] = []
        for rel_path, content in self._files.items():
            full_path = self._output_dir / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            written.append(full_path)
            logger.info("Wrote: %s", full_path)
        return written

    def generate_filelist(self) -> str:
        """Generate a filelist.f for simulation tools."""
        lines = [
            "// Auto-generated filelist for UVM testbench",
            "// Compile order matters — packages first, then components",
            "",
        ]

        # Sort: packages first, then interfaces, then components, then top
        pkg_files = [f for f in self._files if f.endswith("_pkg.sv")]
        intf_files = [f for f in self._files if "_if." in f or "interface" in f.lower()]
        top_files = [f for f in self._files if "top" in f.lower()]
        other_files = [
            f for f in self._files
            if f not in pkg_files and f not in intf_files and f not in top_files
        ]

        for group in [pkg_files, intf_files, other_files, top_files]:
            for f in sorted(group):
                lines.append(f)

        content = "\n".join(lines) + "\n"
        self.add_file("filelist.f", content)
        return content

    def generate_makefile(self, simulator: str = "xcelium") -> str:
        """Generate a basic Makefile for running simulation."""
        if simulator == "xcelium":
            content = _XCELIUM_MAKEFILE
        elif simulator == "vcs":
            content = _VCS_MAKEFILE
        else:
            content = _GENERIC_MAKEFILE

        self.add_file("Makefile", content)
        return content

    @property
    def registered_files(self) -> dict[str, str]:
        return dict(self._files)


_XCELIUM_MAKEFILE = """\
# Auto-generated Makefile for UVM testbench (Xcelium)
TOOL    = xrun
UVM_VER = 1.2
SIM_OPTS = -uvm -uvmhome CDNS-$(UVM_VER) -access +rwc
FILES   = -f filelist.f

.PHONY: compile sim clean

compile:
\t$(TOOL) -compile $(SIM_OPTS) $(FILES)

sim:
\t$(TOOL) $(SIM_OPTS) $(FILES) +UVM_TESTNAME=$(TEST)

clean:
\trm -rf xcelium.d waves.shm *.log *.key
"""

_VCS_MAKEFILE = """\
# Auto-generated Makefile for UVM testbench (VCS)
TOOL    = vcs
SIM_OPTS = -sverilog -ntb_opts uvm-1.2 -debug_access+all
FILES   = -f filelist.f

.PHONY: compile sim clean

compile:
\t$(TOOL) $(SIM_OPTS) $(FILES) -o simv

sim:
\t./simv +UVM_TESTNAME=$(TEST)

clean:
\trm -rf simv simv.daidir csrc *.log *.vpd
"""

_GENERIC_MAKEFILE = """\
# Auto-generated Makefile for UVM testbench
# Adjust SIM_TOOL and SIM_OPTS for your simulator
SIM_TOOL = xrun
SIM_OPTS = -uvm
FILES    = -f filelist.f

.PHONY: sim clean

sim:
\t$(SIM_TOOL) $(SIM_OPTS) $(FILES) +UVM_TESTNAME=$(TEST)

clean:
\trm -rf *.log
"""
