"""Abstract representations of UVM components for code generation."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class UVMComponentType(str, Enum):
    TEST = "uvm_test"
    ENV = "uvm_env"
    AGENT = "uvm_agent"
    DRIVER = "uvm_driver"
    MONITOR = "uvm_monitor"
    SEQUENCER = "uvm_sequencer"
    SEQUENCE = "uvm_sequence"
    SEQUENCE_ITEM = "uvm_sequence_item"
    SCOREBOARD = "uvm_scoreboard"
    SUBSCRIBER = "uvm_subscriber"
    CONFIG = "uvm_object"


class TransactionFieldSpec(BaseModel):
    """A single field in a UVM transaction / sequence item."""

    name: str
    sv_type: str = "logic"
    width: int = 1
    is_rand: bool = True
    constraint_expr: str = ""
    description: str = ""

    @property
    def full_sv_type(self) -> str:
        if self.width <= 1:
            return self.sv_type
        return f"{self.sv_type} [{self.width - 1}:0]"

    @property
    def rand_prefix(self) -> str:
        return "rand " if self.is_rand else ""


class UVMComponentSpec(BaseModel):
    """Base specification for any UVM component."""

    name: str
    component_type: UVMComponentType
    parent_class: str = ""
    description: str = ""
    package_name: str = ""

    def model_post_init(self, __context: object) -> None:
        if not self.parent_class:
            self.parent_class = self.component_type.value


class UVMSequenceItemSpec(UVMComponentSpec):
    """Specification for a UVM sequence item (transaction)."""

    component_type: UVMComponentType = UVMComponentType.SEQUENCE_ITEM
    fields: list[TransactionFieldSpec] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)

    @property
    def rand_fields(self) -> list[TransactionFieldSpec]:
        return [f for f in self.fields if f.is_rand]


class UVMDriverSpec(UVMComponentSpec):
    """Specification for a UVM driver."""

    component_type: UVMComponentType = UVMComponentType.DRIVER
    transaction_type: str = ""
    interface_name: str = ""
    drive_logic_hint: str = ""


class UVMMonitorSpec(UVMComponentSpec):
    """Specification for a UVM monitor."""

    component_type: UVMComponentType = UVMComponentType.MONITOR
    transaction_type: str = ""
    interface_name: str = ""
    sample_logic_hint: str = ""


class UVMSequencerSpec(UVMComponentSpec):
    """Specification for a UVM sequencer."""

    component_type: UVMComponentType = UVMComponentType.SEQUENCER
    transaction_type: str = ""


class UVMSequenceSpec(UVMComponentSpec):
    """Specification for a UVM sequence."""

    component_type: UVMComponentType = UVMComponentType.SEQUENCE
    transaction_type: str = ""
    body_logic_hint: str = ""
    num_items: int = 10
    scenario_description: str = ""


class UVMAgentSpec(UVMComponentSpec):
    """Specification for a UVM agent."""

    component_type: UVMComponentType = UVMComponentType.AGENT
    is_active: bool = True
    transaction_type: str = ""
    interface_name: str = ""
    driver: Optional[UVMDriverSpec] = None
    monitor: Optional[UVMMonitorSpec] = None
    sequencer: Optional[UVMSequencerSpec] = None


class UVMScoreboardSpec(UVMComponentSpec):
    """Specification for a UVM scoreboard."""

    component_type: UVMComponentType = UVMComponentType.SCOREBOARD
    transaction_type: str = ""
    check_logic_hint: str = ""


class UVMEnvSpec(UVMComponentSpec):
    """Specification for a UVM environment."""

    component_type: UVMComponentType = UVMComponentType.ENV
    agents: list[UVMAgentSpec] = Field(default_factory=list)
    scoreboards: list[UVMScoreboardSpec] = Field(default_factory=list)


class UVMTestSpec(UVMComponentSpec):
    """Specification for a UVM test."""

    component_type: UVMComponentType = UVMComponentType.TEST
    env_type: str = ""
    default_sequence: str = ""
    timeout_ns: float = 100000.0
