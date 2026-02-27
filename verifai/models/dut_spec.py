"""Data models for DUT (Design Under Test) specification."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class PortDirection(str, Enum):
    INPUT = "input"
    OUTPUT = "output"
    INOUT = "inout"


class PortSpec(BaseModel):
    """Specification for a single DUT port."""

    name: str
    direction: PortDirection
    width: int = 1
    description: str = ""
    is_clock: bool = False
    is_reset: bool = False

    @property
    def sv_type(self) -> str:
        if self.width == 1:
            return "logic"
        return f"logic [{self.width - 1}:0]"


class ParameterSpec(BaseModel):
    """Specification for a DUT parameter."""

    name: str
    datatype: str = "int"
    default_value: str = ""
    description: str = ""


class ProtocolSpec(BaseModel):
    """Description of a protocol/interface on the DUT."""

    name: str
    port_names: list[str] = Field(default_factory=list)
    protocol_type: str = ""  # e.g. "AXI4", "APB", "custom"
    description: str = ""


class DUTSpec(BaseModel):
    """Complete specification of a Design Under Test."""

    name: str
    module_name: str = ""
    ports: list[PortSpec] = Field(default_factory=list)
    parameters: list[ParameterSpec] = Field(default_factory=list)
    protocols: list[ProtocolSpec] = Field(default_factory=list)
    description: str = ""
    clock_name: str = "clk"
    reset_name: str = "rst_n"
    reset_active_low: bool = True

    def model_post_init(self, __context: object) -> None:
        if not self.module_name:
            self.module_name = self.name

    @property
    def input_ports(self) -> list[PortSpec]:
        return [p for p in self.ports if p.direction == PortDirection.INPUT]

    @property
    def output_ports(self) -> list[PortSpec]:
        return [p for p in self.ports if p.direction == PortDirection.OUTPUT]

    @property
    def clock_port(self) -> Optional[PortSpec]:
        for p in self.ports:
            if p.is_clock:
                return p
        return None

    @property
    def reset_port(self) -> Optional[PortSpec]:
        for p in self.ports:
            if p.is_reset:
                return p
        return None

    @property
    def signal_ports(self) -> list[PortSpec]:
        """Ports that are neither clock nor reset."""
        return [p for p in self.ports if not p.is_clock and not p.is_reset]
