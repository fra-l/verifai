# Proposed New Features

Three features identified by analysing the existing architecture, pain-points
in the current workflow, and natural extension points in the codebase.

---

## Feature 1 — RTL Auto-Parser (`verifai parse-rtl`)

### Problem

Users must hand-write a `dut_spec.json` before they can run `verifai generate`.
Anyone who already has Verilog/SystemVerilog RTL has to manually re-describe
every port, direction, width, and protocol grouping — a tedious and error-prone
step.

### What it does

A new CLI command that reads an existing `.v` / `.sv` RTL file, extracts the
module interface automatically, and emits a ready-to-use `dut_spec.json`.

```
verifai parse-rtl path/to/alu.sv --output alu_spec.json
```

### How it fits the architecture

* **New module**: `verifai/parser/rtl_parser.py`
  * Regex/grammar-based parser for SystemVerilog module headers (ANSI port
    style is the common case).
  * Extracts: module name, port names, directions (`input`/`output`/`inout`),
    widths from packed dimensions, `parameter` declarations.
  * Applies naming heuristics to set `is_clock` / `is_reset` flags
    (e.g. names containing `clk`, `clock`, `rst`, `reset`).
  * Groups ports into `ProtocolSpec` objects using the LLM when heuristics
    alone are insufficient, keeping the parser fast for the common case.
* **New CLI command** added to `verifai/cli/main.py` — no changes to the
  existing `generate` or `plan` commands.
* **Output** is a `DUTSpec` serialised to JSON, directly consumable by
  `verifai generate`.

### Example

Input `alu.sv` module header:
```systemverilog
module alu #(parameter WIDTH = 8) (
  input  logic             clk,
  input  logic             rst_n,
  input  logic [2:0]       opcode,
  input  logic [WIDTH-1:0] operand_a,
  input  logic [WIDTH-1:0] operand_b,
  input  logic             valid_in,
  output logic [WIDTH-1:0] result,
  output logic             valid_out,
  output logic             carry
);
```

Auto-generated `alu_spec.json` (excerpt):
```json
{
  "name": "alu",
  "module_name": "alu",
  "clock_name": "clk",
  "reset_name": "rst_n",
  "reset_active_low": true,
  "ports": [
    {"name": "clk",       "direction": "input",  "width": 1, "is_clock": true},
    {"name": "rst_n",     "direction": "input",  "width": 1, "is_reset": true},
    {"name": "opcode",    "direction": "input",  "width": 3},
    {"name": "operand_a", "direction": "input",  "width": 8},
    ...
  ]
}
```

### Key files to create / modify

| File | Change |
|---|---|
| `verifai/parser/__init__.py` | New package |
| `verifai/parser/rtl_parser.py` | New — regex parser + LLM grouping |
| `verifai/cli/main.py` | Add `parse-rtl` command |
| `tests/test_parser.py` | New — unit tests for the parser |

---

## Feature 2 — Self-Healing Lint Loop

### Problem

Generated SystemVerilog is produced by an LLM and written directly to disk.
There is no step that validates the output is syntactically correct before
handing it to the user. A typo in a generated module port list or a missing
`endclass` means the user only discovers the error when they try to compile.

### What it does

After all files are written, automatically run a lightweight syntax check
(Verilator `--lint-only` or Icarus Verilog `-t null`) on the generated files.
Any lint errors are fed back into the relevant agent as a `ReviewFeedback`
message so it can produce a corrected version. The loop runs up to
`max_lint_rounds` times (configurable, default 3).

```
$ verifai generate alu_spec.json
...
[lint] Checking 12 generated files...
[lint] 2 errors in sequences/alu_seq.sv — sending back to SequenceAgent
[lint] Retry 1/3 — regenerating sequences/alu_seq.sv
[lint] All files clean after 1 retry.
Generation complete!
```

### How it fits the architecture

* **New module**: `verifai/lint/runner.py`
  * Detects which linter is available (`verilator`, `iverilog`, or a
    pure-Python regex fallback for basic checks).
  * Parses linter stderr into structured `LintError` objects
    (file, line, message).
  * Maps each erroring file back to the agent that generated it using the
    `CodeArtifact.component_type` field already present in the model.
* **`OrchestratorAgent._lint_and_heal()`** — new method called from
  `cli/main.py` after `project.write_all()`.
  * Builds a `ReviewFeedback` with `approved=False` and `issues` populated
    from `LintError` objects.
  * Re-publishes the feedback on the `MessageBus` so the originating agent
    handles it exactly as it does an LLM review rejection today.
  * Rewrites only the files that changed.
* **`Settings`** — add `max_lint_rounds: int = 3` and
  `lint_tool: str = "auto"`.

### Key files to create / modify

| File | Change |
|---|---|
| `verifai/lint/__init__.py` | New package |
| `verifai/lint/runner.py` | New — linter invocation + error parsing |
| `verifai/agents/orchestrator.py` | Add `_lint_and_heal()` method |
| `verifai/config/settings.py` | Add `max_lint_rounds`, `lint_tool` |
| `verifai/cli/main.py` | Call `_lint_and_heal()` after `write_all()` |
| `tests/test_lint.py` | New — unit tests with fixture lint output |

---

## Feature 3 — HTML Generation Report

### Problem

After `verifai generate` completes the user sees a short summary line
(`Wrote 12 files`). There is no way to inspect the agent dialogue, understand
*why* a component was generated a particular way, or audit which coverage bins
are targeted by which sequences — short of reading every generated file
manually.

### What it does

Generate a self-contained `report.html` alongside the testbench files. The
report gives a human-readable view of the entire generation session:

* **DUT summary** — port table, parameter list, detected protocols.
* **Testbench plan** — clock/reset settings, coverage target, agents.
* **Component inventory** — collapsible table of every generated file with
  syntax-highlighted source.
* **Agent dialogue log** — the full request/response/review conversation for
  each component so the user can understand the LLM's reasoning.
* **Coverage model summary** — covergroups and coverpoints extracted from the
  generated scoreboard.

No external dependencies: the report is a single HTML file with inline CSS and
minimal vanilla JS for the collapsible sections.

```
$ verifai generate alu_spec.json --report
...
Generation complete!
Report: ./generated_tb/report.html
```

### How it fits the architecture

* **New module**: `verifai/report/generator.py`
  * `ReportGenerator` takes `DUTSpec`, `TestbenchPlan`, the
    `DialogueManager`'s history, and `ProjectManager`'s file dict.
  * Renders a Jinja2 HTML template (reusing the existing Jinja2 dependency).
  * Escapes all user/LLM content — no XSS surface.
* **New template**: `verifai/templates/report.html.j2`
* **`cli/main.py`** — add `--report / --no-report` flag to `generate`.
* **`DialogueManager`** — already stores the full dialogue history; just needs
  a `snapshot()` method to expose it as a serialisable list.

### Key files to create / modify

| File | Change |
|---|---|
| `verifai/report/__init__.py` | New package |
| `verifai/report/generator.py` | New — HTML report builder |
| `verifai/templates/report.html.j2` | New — Jinja2 HTML template |
| `verifai/comms/dialogue.py` | Add `snapshot()` method |
| `verifai/cli/main.py` | Add `--report` flag to `generate` |
| `tests/test_report.py` | New — unit tests for report generation |

---

## Summary

| # | Feature | Value | Effort | New dependencies |
|---|---|---|---|---|
| 1 | RTL Auto-Parser | Removes manual JSON authoring step | Medium | None (regex; optional LLM call) |
| 2 | Self-Healing Lint Loop | Guarantees syntactically valid output | Medium | Verilator or iverilog (optional) |
| 3 | HTML Generation Report | Full auditability of agent decisions | Low–Medium | None (Jinja2 already present) |
