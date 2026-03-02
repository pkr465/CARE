# Sample RTL — CARE Test Suite

A curated set of Verilog and SystemVerilog files for exercising CARE's analysis pipeline.

## Directory Layout

```
sample_rtl/
├── good/               ← Clean, synthesisable reference designs
│   ├── alu.v                8-bit ALU
│   ├── fifo_sync.v          Parameterised synchronous FIFO
│   ├── spi_master.sv        SPI master controller
│   ├── counter_gray.sv      Gray-code counter
│   └── pkg_care_types.svh   Shared type/constant package
│
├── buggy/              ← Intentionally flawed — CARE should flag these
│   ├── cdc_violation.v      CDC: 1-flop sync, raw multi-bit, combo path
│   ├── latch_inferred.v     Incomplete case/if, bad sensitivity list
│   ├── synth_hazards.sv     Blocking in seq, multi-driver, combo loop, dead FSM states
│   └── reset_issues.v       Mixed polarity, async/sync mix, missing resets
│
└── mixed/              ← Functional but with code-quality issues
    ├── uart_tx.v            Magic numbers, unused port, width mismatch
    ├── arbiter_rr.sv        Hardcoded width, naming inconsistency
    └── memory_ctrl.sv       Integer counter, read-during-write, non-synth init
```

## Bug Categories Covered

| Category | Files | Example Issues |
|---|---|---|
| CDC | `cdc_violation.v` | Single-flop sync, multi-bit crossing, combo path |
| Latches | `latch_inferred.v` | Incomplete case, missing else, bad sensitivity list |
| Synthesis | `synth_hazards.sv` | Blocking in always_ff, multi-driver, combo loop |
| Reset | `reset_issues.v` | Mixed polarity, missing reset, reset in combo |
| Style | `uart_tx.v`, `arbiter_rr.sv` | Magic numbers, naming, unused ports |
| Memory | `memory_ctrl.sv` | Read-during-write, integer counter, initial block |

## Usage

Point CARE at the `sample_rtl/` directory to run a full analysis sweep:

```bash
./launch.sh                     # start CARE dashboard
# then paste the path to sample_rtl/ in the codebase input
```

Or analyse a single category:

```bash
# only buggy files
./launch.sh   # then input path: sample_rtl/buggy/
```
