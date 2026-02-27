# verifai

AI-powered UVM testbench generation and verification acceleration.

verifai uses a hierarchy of Claude-backed agents that mirrors the UVM component tree to automatically generate complete SystemVerilog/UVM testbenches from a DUT specification. It can also enter a closed-loop coverage closure cycle, targeting uncovered bins with new stimulus sequences.

---

## Features

- **Automated testbench generation** — produces driver, monitor, sequencer, scoreboard, and coverage model from a JSON spec
- **Multi-agent architecture** — Orchestrator, Environment, UVM Agent, Sequence, and Scoreboard agents collaborate via an async message bus
- **Coverage closure loop** — iteratively refines stimulus until a configurable coverage target is reached
- **Multiple simulator targets** — Xcelium, VCS, or generic Makefile output
- **Jinja2 templates** — all generated SystemVerilog is rendered from parameterized templates, making customization easy

---

## Installation

Requires Python 3.10 or later.

```bash
git clone https://github.com/fra-l/UVM-AI.git
cd UVM-AI
pip install -e .
```

For development dependencies (pytest):

```bash
pip install -e ".[dev]"
```

---

## Configuration

Set **one** of the following environment variables before running:

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | API key from [console.anthropic.com](https://console.anthropic.com) |
| `ANTHROPIC_AUTH_TOKEN` | OAuth bearer token (alternative to API key) |

---

## Usage

### Generate a testbench

```bash
uvm-ai generate examples/simple_alu/dut_spec.json
```

Options:

```
uvm-ai generate <SPEC_FILE> [OPTIONS]

  SPEC_FILE   Path to the DUT specification JSON file

Options:
  -o, --output PATH          Output directory  [default: ./generated_tb]
  --simulator [xcelium|vcs|generic]
                             Target simulator  [default: xcelium]
  --log-level TEXT           Logging level     [default: INFO]
```

### Preview a testbench plan (no code generated)

```bash
uvm-ai plan examples/simple_alu/dut_spec.json
```

---

## DUT Specification Format

The input is a JSON file that describes the DUT's ports and protocols. Example (`examples/simple_alu/dut_spec.json`):

```json
{
  "name": "simple_alu",
  "module_name": "simple_alu",
  "description": "A simple 8-bit ALU with add, subtract, AND, OR operations",
  "clock_name": "clk",
  "reset_name": "rst_n",
  "reset_active_low": true,
  "ports": [
    {"name": "clk",       "direction": "input",  "width": 1, "is_clock": true},
    {"name": "rst_n",     "direction": "input",  "width": 1, "is_reset": true},
    {"name": "opcode",    "direction": "input",  "width": 2},
    {"name": "operand_a", "direction": "input",  "width": 8},
    {"name": "operand_b", "direction": "input",  "width": 8},
    {"name": "valid_in",  "direction": "input",  "width": 1},
    {"name": "result",    "direction": "output", "width": 8},
    {"name": "valid_out", "direction": "output", "width": 1},
    {"name": "carry",     "direction": "output", "width": 1}
  ],
  "protocols": [
    {
      "name": "alu_if",
      "port_names": ["opcode", "operand_a", "operand_b", "valid_in", "result", "valid_out", "carry"],
      "protocol_type": "custom",
      "description": "Simple valid-based handshake"
    }
  ]
}
```

---

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design. In brief:

```
Orchestrator Agent  (≈ uvm_test)
├── Environment Agent           (≈ uvm_env)
│   └── UVM Agent Agent(s)      (≈ uvm_agent)  — one per protocol interface
│       └── Sequence Agent(s)   (≈ uvm_sequence)
└── Scoreboard / Coverage Agent
```

Agents communicate through a typed async `MessageBus`. The orchestrator drives the overall plan and resolves cross-agent conflicts before invoking the code emitter.

---

## Project Structure

```
uvm_ai/
├── agents/       # AI agents (orchestrator, env, uvm_agent, sequence, scoreboard)
├── cli/          # Click-based CLI entry points
├── codegen/      # Template emitter and project/file manager
├── comms/        # MessageBus and DialogueManager
├── config/       # Application settings (Settings, AgentConfig)
├── models/       # Pydantic data models (DUTSpec, TBPlan, messages, …)
└── templates/    # Jinja2 SystemVerilog/UVM templates
examples/
└── simple_alu/   # 8-bit ALU example with RTL and dut_spec.json
```

---

## Technology Stack

| Component | Library |
|---|---|
| LLM backend | [Anthropic Claude](https://www.anthropic.com) (`anthropic` SDK) |
| Data models | Pydantic v2 |
| CLI | Click |
| Templates | Jinja2 |
| Concurrency | asyncio |
| Tests | pytest + pytest-asyncio |
