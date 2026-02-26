"""Application settings and configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    """Configuration for an individual AI agent."""

    model: str = "claude-sonnet-4-6"
    max_tokens: int = 4096
    temperature: float = 0.0
    max_retries: int = 3
    system_prompt_override: str = ""


class Settings(BaseModel):
    """Global application settings."""

    # API — set one of these, not both
    anthropic_api_key: str = ""   # from console.anthropic.com (ANTHROPIC_API_KEY)
    anthropic_auth_token: str = ""  # OAuth bearer token (ANTHROPIC_AUTH_TOKEN)
    default_model: str = "claude-sonnet-4-6"

    # Agent configs
    orchestrator: AgentConfig = Field(default_factory=lambda: AgentConfig(
        model="claude-sonnet-4-6",
        max_tokens=8192,
    ))
    component_agent: AgentConfig = Field(default_factory=AgentConfig)
    sequence_agent: AgentConfig = Field(default_factory=AgentConfig)
    scoreboard_agent: AgentConfig = Field(default_factory=AgentConfig)

    # Code generation
    output_dir: Path = Path("./generated_tb")
    simulator: str = "xcelium"
    uvm_version: str = "1.2"

    # Dialogue
    max_revision_rounds: int = 3
    coverage_target: float = 95.0

    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = None
