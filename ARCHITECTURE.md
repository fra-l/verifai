# verifai Architecture

## Vision

verifai accelerates ASIC verification by using AI agents to automate UVM testbench
construction, stimulus generation, and coverage closure. A hierarchy of specialized
agents mirrors the UVM component tree: an **Orchestrator** manages the testbench,
**Component Agents** generate structural RTL/UVM code, and **Sequence Agents**
create and refine stimulus sequences — all coordinating through a message-based
dialogue protocol.

---

## 1. Agent Hierarchy (maps to UVM hierarchy)

```
┌─────────────────────────────────────────────────────┐
│                 Orchestrator Agent                   │
│  (≈ uvm_test)                                       │
│  Owns the global plan, delegates to sub-agents,     │
│  resolves conflicts, drives coverage closure loop.  │
└──────────┬──────────────────────────┬───────────────┘
           │                          │
    ┌──────▼──────────┐      ┌───────▼────────────┐
    │ Environment Agent│      │ Scoreboard/Coverage│
    │ (≈ uvm_env)     │      │ Agent              │
    │ Assembles agents,│      │ Tracks functional  │
    │ connectivity,    │      │ coverage, checks   │
    │ config objects   │      │ results, suggests  │
    └──────┬───────────┘      │ new sequences      │
           │                  └────────────────────┘
    ┌──────▼──────────┐
    │ UVM Agent Agent  │  (one per interface / protocol)
    │ (≈ uvm_agent)   │
    │ Generates driver,│
    │ monitor,         │
    │ sequencer code   │
    └──────┬───────────┘
           │
    ┌──────▼──────────┐
    │ Sequence Agent   │  (one per sequence family)
    │ (≈ uvm_sequence) │
    │ Creates sequence │
    │ items, virtual   │
    │ sequences,       │
    │ constrained-     │
    │ random stimuli   │
    └─────────────────┘
```

## 2. Inter-Agent Communication Protocol

Agents communicate via a **MessageBus** — an async publish/subscribe system with
typed message channels.

### Message Types

| Message Type        | From               | To                  | Purpose                                         |
|---------------------|--------------------|---------------------|--------------------------------------------------|
| `PlanRequest`       | Orchestrator       | Any sub-agent       | "Generate component X with spec Y"               |
| `PlanResponse`      | Sub-agent          | Orchestrator        | "Here is my proposed code/plan"                   |
| `ReviewFeedback`    | Orchestrator       | Sub-agent           | "Revise: issue with port widths"                  |
| `InterfaceContract` | UVM Agent Agent    | Sequence Agent      | "Here are the transaction fields and constraints" |
| `SequenceProposal`  | Sequence Agent     | Orchestrator        | "Proposed sequence covering scenario X"           |
| `CoverageReport`    | Scoreboard Agent   | Orchestrator        | "Coverage at 73%, gaps in corner cases A, B"      |
| `CoverageDirective` | Orchestrator       | Sequence Agent      | "Target these uncovered bins"                     |
| `CodeArtifact`      | Any agent          | Codegen engine      | "Emit this SystemVerilog file"                    |

### Dialogue Flow (typical session)

```
User provides: DUT spec (ports, protocol, constraints)
  │
  ▼
Orchestrator analyzes DUT → creates TB plan
  │
  ├──► Environment Agent: build env skeleton
  │      └──► UVM Agent Agent(s): build agent(s) for each interface
  │             └──► Sequence Agent(s): build base sequences
  │
  ├──► Scoreboard Agent: build scoreboard + coverage model
  │
  ▼
Orchestrator reviews all artifacts → resolves cross-agent issues
  │
  ▼
Code generation: emit complete UVM testbench
  │
  ▼
(Optional) Coverage closure loop:
  Scoreboard Agent reports gaps → Orchestrator directs Sequence Agent
  → new sequences generated → re-simulate → repeat
```

## 3. Core Modules

### 3.1 `verifai/models/` — Data Models
- `dut_spec.py`       — DUT port list, parameters, protocol descriptions
- `tb_plan.py`        — Testbench plan: which agents, connections, sequences
- `uvm_component.py`  — Abstract representation of any UVM component
- `messages.py`       — All inter-agent message types

### 3.2 `verifai/agents/` — AI Agents
- `orchestrator.py`   — Top-level orchestrator
- `env_agent.py`      — Environment assembly agent
- `uvm_agent_agent.py`— Per-interface UVM agent generator
- `sequence_agent.py` — Stimulus sequence generator
- `scoreboard_agent.py`— Scoreboard + coverage agent

### 3.3 `verifai/comms/` — Communication
- `message_bus.py`    — Async pub/sub message bus
- `dialogue.py`       — Structured dialogue manager (request/response tracking)

### 3.4 `verifai/templates/` — SystemVerilog/UVM Templates
- Jinja2 templates for every UVM component type
- Parameterized by data models

### 3.5 `verifai/codegen/` — Code Generation
- `emitter.py`        — Renders templates with agent-provided data
- `project.py`        — Manages output file tree and Makefile/filelist

### 3.6 `verifai/cli/` — User Interface
- `main.py`           — CLI entry point (click-based)
- `interactive.py`    — Interactive session mode

## 4. Technology Stack

- **Python 3.10+**
- **Anthropic Claude API** (via `anthropic` SDK) for agent LLM calls
- **Jinja2** for SystemVerilog template rendering
- **asyncio** for concurrent agent execution
- **Pydantic** for data models and validation
- **Click** for CLI

## 5. Coverage Closure Loop

The most powerful feature: after initial TB generation, the system can enter a
closed-loop refinement cycle:

1. Run simulation (user provides simulator or we generate scripts)
2. Parse coverage reports
3. Scoreboard Agent identifies coverage holes
4. Orchestrator directs Sequence Agent to create targeted sequences
5. Repeat until coverage target is met

This transforms the tool from a one-shot generator into an iterative verification
assistant.
