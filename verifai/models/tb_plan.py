"""Data models for testbench planning."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class SequencePlan(BaseModel):
    """Plan for a stimulus sequence."""

    name: str
    description: str = ""
    target_agent: str = ""
    scenario: str = ""  # e.g. "basic_read", "burst_write", "error_injection"
    constraints: list[str] = Field(default_factory=list)
    coverage_targets: list[str] = Field(default_factory=list)


class AgentPlan(BaseModel):
    """Plan for a UVM agent."""

    name: str
    interface_name: str = ""
    protocol_type: str = ""
    is_active: bool = True
    has_scoreboard: bool = True
    sequences: list[SequencePlan] = Field(default_factory=list)
    description: str = ""

    @field_validator("sequences", mode="before")
    @classmethod
    def coerce_sequences(cls, v: Any) -> list[Any]:
        if isinstance(v, list):
            return [{"name": item} if isinstance(item, str) else item for item in v]
        return v


class TestbenchPlan(BaseModel):
    """Complete testbench plan produced by the orchestrator."""

    name: str
    dut_name: str
    agents: list[AgentPlan] = Field(default_factory=list)
    top_module_name: str = ""
    clock_period_ns: float = 10.0
    reset_duration_ns: float = 100.0
    simulation_timeout_ns: float = 100000.0
    coverage_target: float = 95.0
    description: str = ""
    additional_notes: list[str] = Field(default_factory=list)

    def model_post_init(self, __context: object) -> None:
        if not self.top_module_name:
            self.top_module_name = f"tb_{self.dut_name}_top"

    @property
    def active_agents(self) -> list[AgentPlan]:
        return [a for a in self.agents if a.is_active]

    @property
    def all_sequences(self) -> list[SequencePlan]:
        seqs: list[SequencePlan] = []
        for agent in self.agents:
            seqs.extend(agent.sequences)
        return seqs
