"""CLI entry point for verifai testbench generation."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

import click

from verifai.config.settings import Settings
from verifai.models.dut_spec import DUTSpec


def _setup_logging(level: str, log_file: str | None = None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=handlers,
    )


@click.group()
@click.option("--log-level", default="INFO", help="Logging level")
@click.pass_context
def cli(ctx: click.Context, log_level: str) -> None:
    """verifai: AI-powered UVM testbench generation."""
    ctx.ensure_object(dict)
    ctx.obj["settings"] = Settings(log_level=log_level)
    _setup_logging(log_level)


@cli.command()
@click.argument("spec_file", type=click.Path(exists=True))
@click.option("--output", "-o", default="./generated_tb", help="Output directory")
@click.option("--simulator", default="xcelium", type=click.Choice(["xcelium", "vcs", "generic"]))
@click.pass_context
def generate(ctx: click.Context, spec_file: str, output: str, simulator: str) -> None:
    """Generate a UVM testbench from a DUT specification file."""
    settings: Settings = ctx.obj["settings"]
    settings.output_dir = Path(output)
    settings.simulator = simulator

    spec_path = Path(spec_file)
    with open(spec_path) as f:
        spec_data = json.load(f)

    dut_spec = DUTSpec(**spec_data)
    click.echo(f"Generating testbench for DUT: {dut_spec.name}")
    click.echo(f"  Ports: {len(dut_spec.ports)}")
    click.echo(f"  Output: {output}")

    asyncio.run(_run_generation(settings, dut_spec))
    click.echo("Generation complete!")


async def _run_generation(settings: Settings, dut_spec: DUTSpec) -> None:
    """Run the full testbench generation pipeline."""
    from verifai.codegen.emitter import TemplateEmitter
    from verifai.codegen.project import ProjectManager
    from verifai.comms.dialogue import DialogueManager
    from verifai.comms.message_bus import MessageBus
    from verifai.agents.orchestrator import OrchestratorAgent

    bus = MessageBus()
    dialogue_mgr = DialogueManager(max_revisions=settings.max_revision_rounds)
    emitter = TemplateEmitter()
    project = ProjectManager(settings.output_dir)

    orchestrator = OrchestratorAgent(
        config=settings.orchestrator,
        bus=bus,
        dialogue_mgr=dialogue_mgr,
        emitter=emitter,
        project=project,
        api_key=settings.anthropic_api_key,
        base_url=settings.ollama_base_url,
        auth_token=settings.anthropic_auth_token,
    )

    plan = await orchestrator.analyze_dut(dut_spec)
    click.echo(f"  Plan: {plan.name} ({len(plan.agents)} agents)")

    await orchestrator.generate_components(dut_spec, plan)

    # Generate and write output
    project.generate_filelist()
    project.generate_makefile(settings.simulator)
    written = project.write_all()
    click.echo(f"  Wrote {len(written)} files")


@cli.command()
@click.argument("spec_file", type=click.Path(exists=True))
@click.pass_context
def plan(ctx: click.Context, spec_file: str) -> None:
    """Show a testbench plan without generating code."""
    spec_path = Path(spec_file)
    with open(spec_path) as f:
        spec_data = json.load(f)

    dut_spec = DUTSpec(**spec_data)
    click.echo(f"DUT: {dut_spec.name} ({dut_spec.module_name})")
    click.echo(f"  Ports: {len(dut_spec.ports)}")
    for port in dut_spec.ports:
        click.echo(f"    {port.direction.value:6s} {port.sv_type:20s} {port.name}")
    click.echo(f"  Protocols: {len(dut_spec.protocols)}")
    for proto in dut_spec.protocols:
        click.echo(f"    {proto.name} ({proto.protocol_type})")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
