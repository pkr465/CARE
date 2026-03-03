# CARE — Codebase Analysis & Repair Engine for HDL

Multi-agent static analysis and AI-assisted design review framework for **Verilog/SystemVerilog** hardware design codebases. CARE provides a complete pipeline for analyzing RTL designs, generating health metrics, structural hierarchy analysis, and design quality reports — then optionally repairing issues with LLM-guided patches.

---

## Quick Start

```bash
git clone <repo>
cd CARE
chmod +x install.sh
./install.sh            # one-command setup (macOS, Linux, WSL)
./launch.sh             # start the Streamlit dashboard on port 8502
```

The installer detects your OS and package manager (Homebrew, apt, dnf, yum, pacman), installs Python 3.9+, creates a `.venv`, installs all Python deps, and optionally installs HDL tools (Verible, Verilator, Yosys, Icarus Verilog).

```bash
# Skip parts with environment variables
CARE_SKIP_HDL=1 ./install.sh        # skip HDL tools
CARE_SKIP_DB=1 ./install.sh         # skip database setup info
CARE_SKIP_OPTIONAL=1 ./install.sh   # skip Pandoc, mmdc
CARE_PYTHON=python3.11 ./install.sh # override Python binary
```

### Run CLI Analysis

```bash
source .venv/bin/activate
export LLM_API_KEY="sk-..."

python main.py --rtl-path ./rtl --out-dir ./out             # static only
python main.py --rtl-path ./rtl --use-llm                   # static + LLM review
python main.py --rtl-path ./rtl --use-llm --llm-exclusive   # LLM review only
python main.py --rtl-path ./rtl --enable-deep-analysis      # deep adapters (Verilator, Verible)
```

### Launch the Dashboard

```bash
./launch.sh                # Streamlit UI at http://localhost:8502
./launch.sh --website      # also open the silicon design website
./launch.sh --port 8503    # custom port
```

---

## Architecture

CARE is structured as a layered, multi-agent system. The diagram below shows the full pipeline:

```
                            ┌───────────────────────────┐
                            │      CLI / Streamlit UI   │
                            └─────────┬─────────────────┘
                                      │
                       ┌──────────────▼──────────────┐
                       │     AnalysisFramework        │
                       │        (main.py)             │
                       └──────────┬───────────────────┘
                                  │
          ┌───────────────────────┼──────────────────────────┐
          │                       │                          │
    ┌─────▼──────┐   ┌───────────▼───────────┐   ┌──────────▼─────────┐
    │ PostgreSQL  │   │ StaticAnalyzerAgent   │   │  LLM Agents        │
    │   Setup     │   │  (7-phase pipeline)   │   │ (Fixer / Patch /   │
    │ (optional)  │   │                       │   │  Chat / Review)    │
    └─────────────┘   └───────┬───────────────┘   └──────────┬─────────┘
                              │                              │
         ┌────────────────────┼────────────────────┐         │
         │                    │                    │         │
   ┌─────▼─────┐   ┌─────────▼────────┐   ┌──────▼───────┐ │
   │  9 HDL    │   │  7 Deep Analysis │   │ 7 Dependency │ │
   │ Analyzers │   │    Adapters      │   │   Services   │ │
   └───────────┘   └──────────────────┘   └──────────────┘ │
                              │                              │
                    ┌─────────▼──────────────────────────────▼──┐
                    │          Output & Ingestion                │
                    │  designhealth.json  │  Excel  │  HTML/PDF │
                    │  NDJSON  │  Vector DB  │  Diagrams         │
                    └───────────────────────────────────────────┘
```

### 7-Phase Static Analysis Pipeline

The `StaticAnalyzerAgent` runs 7 phases in sequence:

1. **File Discovery** — Scans the codebase for `.v`, `.sv`, `.svh`, `.vh` HDL source files; caches source with per-file metrics.
1b. **Design Context Building** — Discovers and parses constraint/configuration files (`.sdc`, `.tcl`, `.swl`, `.blk`, `.vblk`, `.desc`) to build a unified `DesignContext` with clock definitions, timing constraints, DRC waivers, block hierarchy, and register maps.
2. **Source Parsing** — Extracts module definitions, interfaces, packages, port lists, and parameter declarations.
3. **Hierarchy Building** — Constructs the module instantiation graph using regex (or Verible when available).
4. **9 HDL Analyzers** — Runs all analyzers via `MetricsCalculator` producing per-file and aggregate scores. Analyzers receive the `DesignContext` for enriched analysis (e.g., CDC analyzer uses SDC-defined clocks instead of regex inference; Synthesis Safety applies DRC waivers from `.swl` files).
5. **Metric Aggregation** — Computes weighted health score (0–100, A–F grade) with gate conditions for critical issues.
6. **Report Generation** — Writes `designhealth.json`, Excel workbooks, optional HTML reports, and email notifications.
7. **Visualization** — Generates Mermaid diagrams for module hierarchy, dependency graphs, and architecture views.

---

## Supported File Types

CARE scans two categories of files:

**HDL Source Files** — analyzed by all 9 analyzers and LLM agents:

| Extension | Language | Description |
|---|---|---|
| `.v` | Verilog | Verilog source files |
| `.sv` | SystemVerilog | SystemVerilog source files |
| `.svh` | SystemVerilog | SystemVerilog header files |
| `.vh` | Verilog | Verilog header files |

**Design Constraint & Context Files** — parsed to enrich analyzer and LLM accuracy:

| Extension | Type | Description | Parser |
|---|---|---|---|
| `.sdc` | Timing Constraints | Synopsys Design Constraints — clock definitions, false paths, I/O delays, clock groups | SDCParser |
| `.tcl` | Synthesis Scripts | Tool Command Language — `set_dont_touch`, `set_max_fanout`, synthesis attributes | TCLParser |
| `.swl` | DRC Waivers | PLD Rule Check waivers — suppress known-good DRC violations by rule ID, scope, target | SWLParser |
| `.blk` | Block Descriptors | Block-level hierarchy — parent/child relationships, power domains, port lists | BLKParser |
| `.vblk` | Virtual Blocks | Virtual block/partition definitions — power intent, UPF-style annotations | VBLKParser |
| `.desc` | Register Maps | Design descriptors — register address maps, field definitions, access types | DESCParser |

---

## Design Context Integration

When constraint files are present in the codebase, CARE's Phase 1B builds a unified `DesignContext` object that is injected into analyzers and LLM agents. This provides several accuracy improvements:

**CDC Analyzer** — Uses SDC-defined clocks (`create_clock`) as the authoritative domain list instead of inferring from `posedge`/`negedge` patterns. False paths declared via `set_false_path` automatically downgrade matching CDC violations to informational. Clock groups from `set_clock_groups` identify intentionally asynchronous domains.

**Synthesis Safety Analyzer** — Filters detected DRC violations against `.swl` waivers. Waived violations are still reported but flagged with `waived: true` and don't count toward score deductions.

**Signal Integrity Analyzer** — Uses block boundary definitions from `.blk` files to understand hierarchical partitions when checking port connections.

**LLM Agents** — A formatted design context summary (clocks, constraints, waivers, blocks, registers) is injected into each code chunk's context window, giving the LLM awareness of timing intent and design structure.

Configuration is in the `design_context` section of `global_config.yaml` — see the Configuration section below for details.

---

## Analyzers

CARE ships with 9 specialized HDL analyzers that run on every analysis. Each produces a 0–100 score and A–F grade.

### CDC Analyzer (Clock Domain Crossing)

Detects signals crossing clock domains without proper synchronization. Identifies distinct clock domains by parsing `posedge`/`negedge` edge references (excluding reset signals like `rst_n`), then checks each always/module block for multi-clock usage. When SDC constraints are available, uses declared clocks as the authoritative domain list and suppresses false-path-waived crossings.

**Detects:** single-flop synchronizers (need 2+ stages), multi-bit CDC without gray code or handshake, combinational paths across clock domains, reset domain crossing violations.

### Synthesis Safety Analyzer

Pattern-based Design Rule Check (DRC) engine with 13 rules covering the most common synthesis hazards. Each rule has a severity (critical/high/medium/low) and a DRC code (HDL-DRC-001 through HDL-DRC-013).

**Detects:** combinational loops, latch inference in combinational always blocks, incomplete sensitivity lists, CDC without synchronizer, metastability risks, uninitialized registers, blocking assignments in sequential logic, tri-state in FPGA, X-propagation, clock gating without cells, async FIFO without gray code.

### Quality Analyzer

Scores code quality against HDL best practices and style rules. Checks both anti-patterns (HDL001–HDL008) and style violations (line length, tabs, trailing whitespace, TODO/FIXME markers).

**Detects:** blocking assignments in sequential blocks (`always_ff`), non-blocking in combinational blocks, incomplete sensitivity lists, `initial` blocks in synthesizable RTL, implicit net declarations, `#delay` in synthesis code, multiple drivers on same signal, missing `default` in case statements.

### Complexity Analyzer

Measures cyclomatic complexity (CC), cognitive complexity, nesting depth, boolean expression density, and statement count for every always/generate/function/task block.

**Metrics:** average CC, median CC, P90 CC, max CC, max nesting depth, long blocks (>80 LOC), very long blocks (>200 LOC), deep nesting blocks, boolean-heavy blocks.

### Signal Integrity Analyzer

Detects electrical and structural integrity issues in signal assignments and connections.

**Detects:** multiple drivers on same net (bus contention), bit-width mismatch in assignments, signed/unsigned mismatch, array index out of bounds, port connection width mismatch, inout port misuse, memory inference issues.

### Uninitialized Signal Analyzer

Finds signals that may carry unknown values (`X`/`Z`) due to missing initialization or incomplete assignments.

**Detects:** registers without reset values, signals read before assignment, output ports potentially unconnected, missing else clauses causing latch inference, wire declarations without drivers, incomplete case statements without default.

### Documentation Analyzer

Scores documentation coverage by measuring comment density, module-level documentation, port descriptions, parameter documentation, timescale declarations, clock domain annotations, and reset strategy notes.

### Maintainability Analyzer

Computes a Maintainability Index (SEI-style, 0–100) from LOC metrics, comment ratio, cyclomatic complexity, and Halstead volume. Also checks for include guards, formatting issues, and HDL anti-patterns.

### Verification Coverage Analyzer

Assesses test and verification infrastructure by detecting testbench files, verification framework usage (UVM, SVA, Cocotb, VUnit), assertion coverage, covergroup definitions, and test directory organization.

---

## Deep Analysis Adapters

When `--enable-deep-analysis` is passed, 7 adapters run using external HDL tools (Verilator, Verible) with graceful regex fallback when tools are unavailable. All adapters inherit from `BaseStaticAdapter` and produce a standardized output schema (`score`, `grade`, `metrics`, `issues`, `details`, `tool_available`).

| Adapter | Class | Backend | Purpose |
|---|---|---|---|
| **HDL Complexity** | `HDLComplexityAdapter` | Verilator + fallback | AST-accurate cyclomatic complexity, nesting depth, expression depth |
| **Hierarchy/Call Graph** | `HierarchyAnalyzerAdapter` | Regex | Module instantiation graph, fan-in/fan-out, cycle detection, hierarchy depth |
| **Unused Module Detector** | `UnusedModuleAdapter` | Regex | BFS from top-level modules to find uninstantiated (dead) modules |
| **Module Metrics** | `ModuleMetricsAdapter` | Regex | Per-module port count, LOC, latch risk, generate usage, parameterization |
| **HDL Lint** | `LintAdapter` | Verilator/Verible + fallback | DRC-coded lint violations (HDL-001 through HDL-009) for sequential, combinational, synthesis, and style rules |
| **Dependency Graph** | `DependencyGraphAdapter` | Regex/Verible | Module hierarchy, include tree, package imports, symbol table scoring |
| **Excel Report** | `ExcelReportAdapter` | openpyxl | Generates `static_*` prefixed tabs in the combined Excel output |

---

## Dependency Analysis Services

The `HDLDependencyAnalyzer` orchestrates 7 specialized services that build a comprehensive structural model of the HDL codebase:

| Service | Class | Analyzes |
|---|---|---|
| **Module Hierarchy** | `ModuleHierarchyBuilder` | Instantiation tree, fan-in/fan-out, cycle detection, architectural patterns |
| **Include Dependencies** | `IncludeDependencyGraph` | `` directives, transitive includes, circular chains, unresolved paths |
| **Package Imports** | `PackageImportResolver` | `import` statements, package-to-symbol mapping, unresolved references |
| **Parameter Propagation** | `ParameterPropagationTracker` | Parameter declarations, overrides in instantiations, type mismatch detection |
| **Interface Bindings** | `InterfaceBindingAnalyzer` | Interface/modport definitions, bindings in module ports, unconnected interfaces |
| **Generate Blocks** | `GenerateBlockExpander` | `generate`/`endgenerate`, conditional instantiation mapping |
| **Symbol Table** | `SymbolTableBuilder` | Cross-file symbol resolution, port/signal types, macro definitions, collision detection |

---

## LLM Agents

CARE includes 5 LLM-powered agents for semantic analysis, repair, and interactive exploration:

### StaticAnalyzerAgent
The primary analysis orchestrator. Runs the 7-phase pipeline with optional LLM enrichment in Phase 5 (codebase insights, dependency analysis, documentation recommendations). Produces the canonical `designhealth.json`.

### CodebaseLLMAgent
Per-module semantic design review using multi-turn LLM orchestration. Integrates with the vector database for RAG (retrieval-augmented generation) and the HITL feedback store for learning from human reviews. Produces `design_review.xlsx`.

### CodebaseFixerAgent
Analyzes detected issues from static analysis and generates LLM-powered remediation suggestions prioritized by severity. Produces fix recommendations with explanations and confidence scores.

### CodebasePatchAgent
Single-file patch/diff analysis. Parses unified diffs, reconstructs patched HDL, gathers 4-layer context (module context, synthesis constraints, CDC analysis, signal dependencies), and sends hunk-scoped code to the LLM. Writes findings to Excel patch tabs.

### CodebaseBatchPatchAgent
Multi-file patch application. Parses patches with `===` file headers, applies diffs to corresponding source files, writes patched copies to `out/patched_files/` preserving folder structure. Supports dry-run mode.

### CodebaseAnalysisChatAgent
Interactive conversational HDL analysis with multi-turn state management, vector database semantic search, intent extraction, and criteria-based filtering. Returns JSON-structured responses for chatbot integration.

---

## HITL (Human-in-the-Loop) Feedback System

PostgreSQL-backed persistent store enabling agents to learn from accumulated human design review history. Located in `hitl/`.

**Core components:** `HITLContext` (unified agent interface), `FeedbackStore` (PostgreSQL with 3 tables: decisions, constraint rules, run metadata), `RAGRetriever` (ranked retrieval by recency and action priority), `ConstraintParser` (parses markdown design rule tables), `HITLPromptTemplates` (prompt prefixes injecting RAG context).

**Workflow:** human reviews issues in Excel → feedback is persisted → RAG retriever provides context on future runs → agents skip known false positives and apply learned constraints.

---

## Configuration

### global_config.yaml

Hierarchical YAML configuration with `${ENV_VAR}` substitution for secrets:

| Section | Purpose |
|---|---|
| `paths` | RTL source directory, output directories, prompt template locations |
| `llm` | Provider toggle (`anthropic`/`qgenie`), model selection (`provider::model`), API keys, request defaults |
| `database` | PostgreSQL connection, SSL, pool tuning, vector DB backend |
| `scanning` | Directory/glob exclusions for HDL analysis (sim_results, synthesis, .Xil, etc.) |
| `design_context` | Constraint file discovery patterns, injection toggles (SDC clocks, false paths, DRC waivers, block boundaries), LLM context size limit |
| `hierarchy_builder` | Verible/Verilator executables, timeouts, cache settings, hierarchy depth limits |
| `context` | Include file resolution depth, max context chars, system package exclusions |
| `synthesis` | Target technology (fpga/asic), clock period, reset strategy |
| `eda_tools` | Paths to Verilator, Verible, Yosys, Icarus Verilog |
| `hitl` | Feedback store enable, RAG settings, constraint file patterns |
| `telemetry` | Silent PostgreSQL-backed usage tracking |
| `email` | SMTP configuration for report delivery |
| `excel` | Spreadsheet styling (colors, column widths, freeze/filter) |

### Environment Variables (.env)

The `.env` file holds only API keys. Everything else lives in `global_config.yaml`.

```bash
LLM_API_KEY=""          # Required for LLM analysis (any provider)
QGENIE_API_KEY=""       # Optional, for QGenie models
```

---

## Project Layout

```
.
├── main.py                             # CLI entry point & pipeline orchestrator
├── fixer_workflow.py                   # Analysis → LLM fixes → patch application
├── generate_design_doc.py             # Auto-generate CARE design document (.docx)
├── global_config.yaml                  # Hierarchical YAML configuration
├── requirements.txt                    # Python dependencies
├── install.sh                          # Cross-platform installer
├── launch.sh                           # Dashboard launcher
├── index.html                          # Silicon design website (dark theme)
├── run_e2e_test.py                     # End-to-end analyzer test harness
├── bootstrap_db.sh / .ps1             # PostgreSQL + pgvector setup
├── env.example                         # .env template
├── sample_rtl/                         # Sample Verilog/SV files for testing
│   ├── good/                           #   Clean, synthesisable references
│   ├── buggy/                          #   Intentional bugs (CDC, latch, synth hazards)
│   ├── mixed/                          #   Functional but with style issues
│   ├── constraints/                    #   SDC timing + TCL synthesis directives
│   │   ├── timing.sdc                  #     Clocks, false paths, I/O delays
│   │   └── synthesis.tcl               #     dont_touch, max_fanout, attributes
│   ├── pldrc/                          #   DRC waiver files
│   │   └── waivers.swl                 #     3 DRC waivers for sample_rtl issues
│   ├── blocks/                         #   Block hierarchy definitions
│   │   └── top.blk                     #     SoC block hierarchy + power domains
│   └── regs/                           #   Register map descriptors
│       └── uart_regs.desc              #     UART TX register map (6 registers)
│
├── agents/
│   ├── codebase_static_agent.py        # Unified 7-phase HDL analysis pipeline
│   ├── codebase_llm_agent.py           # LLM-powered semantic design review
│   ├── codebase_fixer_agent.py         # Auto-repair suggestion agent
│   ├── codebase_patch_agent.py         # Single-file diff analysis
│   ├── codebase_batch_patch_agent.py   # Multi-file patch application
│   ├── codebase_analysis_chat_agent.py # Interactive conversational analysis
│   │
│   ├── analyzers/                      # 9 HDL-specific static analyzers
│   │   ├── base_runtime_analyzer.py    #   Base class with shared parsing
│   │   ├── cdc_analyzer.py             #   Clock domain crossing analysis
│   │   ├── synthesis_safety_analyzer.py#   DRC-coded synthesis safety (13 rules)
│   │   ├── quality_analyzer.py         #   Code quality scoring (8 HDL + 4 style)
│   │   ├── complexity_analyzer.py      #   CC, cognitive complexity, nesting
│   │   ├── signal_integrity_analyzer.py#   Multi-driver, width mismatch, contention
│   │   ├── uninitialized_signal_analyzer.py # Missing resets, undriven signals
│   │   ├── documentation_analyzer.py   #   Comment coverage, design docs
│   │   ├── maintainability_analyzer.py #   Maintainability Index (SEI-style)
│   │   ├── verification_coverage_analyzer.py # Testbench/assertion coverage
│   │   └── dependency_analyzer.py      #   Orchestrates 7 dependency services
│   │
│   ├── adapters/                       # Deep analysis (Verilator/Verible + fallback)
│   │   ├── base_adapter.py             #   BaseStaticAdapter ABC
│   │   ├── ast_complexity_adapter.py   #   AST-accurate complexity
│   │   ├── call_graph_adapter.py       #   Module hierarchy graph
│   │   ├── dead_code_adapter.py        #   Unused module detection
│   │   ├── function_metrics_adapter.py #   Per-module port/LOC metrics
│   │   ├── security_adapter.py         #   HDL lint (DRC codes)
│   │   ├── dependency_graph_adapter.py #   Dependency scoring
│   │   └── excel_report_adapter.py     #   Excel tab generation
│   │
│   ├── services/                       # Dependency analysis services
│   │   ├── module_hierarchy_builder.py #   Instantiation tree
│   │   ├── include_dependency_graph.py #   `include resolution
│   │   ├── package_import_resolver.py  #   Package import chains
│   │   ├── parameter_propagation_tracker.py # Parameter overrides
│   │   ├── interface_binding_analyzer.py #  Interface/modport bindings
│   │   ├── generate_block_expander.py  #   Generate block expansion
│   │   └── symbol_table_builder.py     #   Cross-file symbol resolution
│   │
│   ├── core/                           # Pipeline infrastructure
│   │   ├── file_processor.py           #   HDL file discovery & caching
│   │   ├── metrics_calculator.py       #   Analyzer orchestration & scoring
│   │   └── verible_parser_wrapper.py   #   Verible AST integration
│   │
│   ├── context/                        # Design + LLM context builders
│   │   ├── design_context.py           #   Dataclasses for clocks, constraints, waivers, blocks, registers
│   │   ├── design_context_builder.py   #   6 parsers (SDC, TCL, SWL, BLK, VBLK, DESC) + orchestrator
│   │   └── header_context_builder.py   #   Include/macro context injection
│   │
│   ├── prompts/                        # LLM prompt templates
│   │   └── prompts.py                  #   HDL-specific prompts
│   │
│   ├── parsers/                        # Report generators
│   │   ├── healthreport_generator.py   #   HTML health report
│   │   ├── healthreport_parser.py      #   Health report parsing
│   │   └── excel_to_agent_parser.py    #   Excel feedback → directives
│   │
│   ├── reports/                        # PDF report generators
│   │   ├── complexity_report_pdf.py    #   ReportLab complexity PDF
│   │   └── dependency_report_pdf.py    #   ReportLab dependency PDF
│   │
│   ├── visualization/                  # Diagram generation
│   │   └── graph_generator.py          #   Mermaid diagrams
│   │
│   └── vector_db/                      # Vector DB document preparation
│       └── document_processor.py       #   Chunking & embedding prep
│
├── utils/
│   ├── common/
│   │   ├── llm_tools.py                # Multi-provider LLM router
│   │   ├── llm_tools_anthropic.py      # Anthropic Claude SDK
│   │   ├── llm_tools_qgenie.py         # QGenie SDK via LangChain
│   │   ├── email_reporter.py           # SMTP report delivery
│   │   └── excel_writer.py             # Professional Excel workbooks
│   ├── parsers/
│   │   ├── global_config_parser.py     # YAML config + ${ENV_VAR} resolution
│   │   └── env_parser.py               # .env file loader
│   └── data/                           # Re-exports from db/ for import convenience
│       ├── json_flattener.py           # Report → flat JSON
│       ├── ndjson_processor.py         # JSON → NDJSON (embedding-ready)
│       └── vector_db_pipeline.py       # PostgreSQL/pgvector ingestion
│
├── hitl/                               # Human-in-the-loop feedback system
│   ├── hitl_context.py                 # Unified agent interface + FeedbackStore
│   ├── rag_retriever.py                # Ranked RAG retrieval
│   ├── constraint_parser.py            # Markdown design rule parsing
│   ├── excel_feedback_parser.py        # Excel → FeedbackDecision
│   ├── prompts.py                      # HITL prompt templates
│   └── config.py                       # HITL configuration
│
├── db/
│   ├── postgres_db_setup.py            # Schema creation & migrations
│   ├── postgres_api.py                 # PostgreSQL query API
│   ├── json_flattner.py               # Report → flat JSON (JsonFlattener)
│   ├── ndjson_processor.py            # JSON → NDJSON (NDJSONProcessor)
│   ├── ndjson_writer.py               # NDJSON file writer
│   ├── vectordb_pipeline.py           # PostgreSQL/pgvector ingestion
│   ├── vectordb_wrapper.py            # Vector DB connection wrapper
│   ├── telemetry_service.py           # Usage telemetry service
│   ├── schema_codebase_analytics.sql   # Analytics tables
│   ├── schema_telemetry.sql            # Telemetry tables
│   └── pgvector*.sql                   # pgvector extensions & roles
│
├── ui/
│   ├── app.py                          # Streamlit dashboard (dark silicon theme)
│   ├── launch.py                       # Python-based launcher
│   ├── streamlit_tools.py              # Shared UI components & CSS
│   ├── background_workers.py           # Thread-based analysis workers
│   ├── feedback_helpers.py             # HITL feedback UI widgets
│   └── qa_inspector.py                 # QA traceability inspector
│
├── prompts/                            # System & user prompt templates
└── out/                                # Output directory
    ├── designhealth.json               # Canonical design health report
    ├── design_review.xlsx              # LLM semantic analysis results
    ├── static_analysis.xlsx            # Static analysis DRC findings
    ├── diagrams/                       # Module hierarchy diagrams
    ├── pdfs/                           # Complexity & dependency PDFs
    └── parseddata/                     # Flattened JSON & NDJSON
```

---

## Output Artifacts

| File | Description |
|---|---|
| `designhealth.json` | Canonical health report: all 9 analyzer scores, per-file metrics, dependency graph, file cache |
| `design_review.xlsx` | LLM semantic analysis results per module with `static_*` adapter tabs when deep analysis enabled |
| `static_analysis.xlsx` | DRC-coded static analysis findings with severity, line numbers, and fix suggestions |
| `health_report.html` | Interactive HTML dashboard with health scores, charts, and drill-down |
| `*.pdf` | Professional complexity and dependency reports (ReportLab) |
| `*.ndjson` | Embedding-ready documents for vector DB ingestion |
| `diagrams/` | Mermaid module hierarchy and architecture diagrams |

---

## Command-Line Reference

```
RTL/Source Path:
  --rtl-path PATH              Root directory of RTL source code (default: ./rtl)
  --codebase-path PATH         Alias for --rtl-path

Output & Configuration:
  --out-dir DIR                Output directory (default: ./out)
  --config-file FILE           Custom global_config.yaml path

HDL Analysis:
  --use-verible                Enable Verible parser integration
  --enable-deep-analysis       Enable Verilator/Verible deep adapters
  --target-technology TYPE     fpga | asic
  --clock-period NS            Target clock period in nanoseconds
  --reset-strategy STRATEGY    async | sync

LLM Configuration:
  --use-llm                    Enable LLM analysis phase
  --llm-exclusive              Run LLM analysis only (skip static analyzer)
  --llm-model MODEL            Model in 'provider::name' format
  --llm-api-key KEY            API Key override
  --llm-max-tokens TOKENS      Token limit (default: 16384)
  --llm-temperature TEMP       Sampling temperature (default: 0.1)

Vector DB (PostgreSQL):
  --enable-vector-db           Ingest results into PostgreSQL
  --vector-chunk-size INT      Characters per chunk (default: 512)
  --vector-overlap-size INT    Overlap between chunks (default: 128)

HITL (Human-in-the-Loop):
  --enable-hitl                Enable feedback store
  --hitl-feedback-excel FILE   Excel file with human reviews
  --hitl-constraints-dir DIR   Directory with design rule markdown files

Output & Reporting:
  --generate-visualizations    Create module hierarchy diagrams
  --generate-pdfs              Generate PDF design documentation
  --generate-report            Create HTML design health report
  --max-files INT              Limit analysis to N files
  --batch-size INT             Batch size for LLM processing (default: 5)
  --memory-limit MB            Memory limit for analysis
  --force-reanalysis           Re-analyze all files (ignore cache)

Debugging:
  -v, --verbose                Detailed logging
  -D, --debug                  Debug mode with full tracebacks
```

---

## Examples

### Static-Only Analysis

```bash
python main.py --rtl-path ./designs/my_soc --out-dir ./results -v
```

### LLM Design Review

```bash
python main.py \
  --rtl-path ./designs/my_soc \
  --use-llm \
  --llm-model "anthropic::claude-sonnet-4-20250514" \
  --generate-visualizations
```

### Deep Analysis with Adapters

```bash
python main.py \
  --rtl-path ./rtl \
  --enable-deep-analysis \
  --target-technology fpga \
  --clock-period 5.0
```

### Vector DB Ingestion for Semantic Search

```bash
python main.py \
  --rtl-path ./rtl \
  --enable-vector-db \
  --use-llm \
  --vector-chunk-size 1024
```

### Design Repair Workflow

```bash
# 1. Generate design review
python main.py --rtl-path ./rtl --use-llm --llm-exclusive -v

# 2. Review out/design_review.xlsx, mark issues for fixing

# 3. Apply LLM-guided repairs
python fixer_workflow.py \
  --excel-file ./out/design_review.xlsx \
  --rtl-path ./rtl \
  --llm-model "anthropic::claude-sonnet-4-20250514"
```

### End-to-End Analyzer Test

```bash
python run_e2e_test.py    # runs all 6 analyzers on sample_rtl/
```

---

## Multi-Provider LLM Support

CARE supports 4 LLM providers via the `provider::model_name` format:

| Provider | Example Model String | SDK |
|---|---|---|
| Anthropic | `anthropic::claude-sonnet-4-20250514` | anthropic |
| QGenie | `qgenie::qwen2.5-14b-1m` | qgenie.integrations.langchain |
| Vertex AI | `vertexai::gemini-2.5-pro` | langchain_google_vertexai |
| Azure OpenAI | `azure::gpt-4.1` | langchain_openai.AzureChatOpenAI |

Switch providers by changing the `llm.llm_provider` and `llm.model` fields in `global_config.yaml`.

---

## Troubleshooting

**Installation issues:** Run `bash -x ./install.sh 2>&1 | tee install.log` for verbose output. On Windows, run inside WSL.

**Verible/Verilator not found:** Install with `sudo apt-get install verible verilator` (Ubuntu) or `brew install verible verilator` (macOS). CARE degrades gracefully to regex when tools are unavailable.

**PostgreSQL connection error:** Check credentials in `global_config.yaml` under `database:`. Test with `psql -h localhost -U codebase_analytics_user -d codebase_analytics_db`.

**Out of memory:** Use `--memory-limit 4096 --batch-size 2` to reduce footprint.

**Dashboard won't start:** Verify Streamlit (`python -c "import streamlit"`), check port (`lsof -i :8502`), or try `./launch.sh --port 8503`.

---

## License

See LICENSE file for terms.

## Authors

Pavan R — CARE framework for Verilog/SystemVerilog HDL

## Contact

For issues, feature requests, or questions, please open a GitHub issue or contact the maintainers.
