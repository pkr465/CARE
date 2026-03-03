"""
Design context data models for constraint and configuration files.

Provides structured representations of:
- SDC timing constraints (clocks, false paths, delays)
- TCL synthesis directives
- DRC waivers (.swl)
- Block definitions (.blk, .vblk)
- Register maps (.desc)

All models are pure dataclasses with no external dependencies.
"""

import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional, Tuple


# ---------------------------------------------------------------------------
# Clock & Timing
# ---------------------------------------------------------------------------

@dataclass
class ClockDefinition:
    """A clock domain defined in an SDC file."""
    name: str
    period_ns: float
    duty_cycle: float = 0.5
    waveform: Optional[Tuple[float, float]] = None  # (rise_edge, fall_edge)
    source_port: Optional[str] = None
    is_generated: bool = False
    master_clock: Optional[str] = None
    divide_by: Optional[int] = None
    multiply_by: Optional[int] = None
    source_file: str = ""
    line_number: int = 0


@dataclass
class TimingConstraint:
    """A timing constraint from an SDC file."""
    constraint_type: str  # false_path, multicycle_path, input_delay, output_delay, max_delay, min_delay
    from_signal: Optional[str] = None
    to_signal: Optional[str] = None
    from_clock: Optional[str] = None
    to_clock: Optional[str] = None
    delay_ns: Optional[float] = None
    cycles: Optional[int] = None
    clock_ref: Optional[str] = None
    comment: Optional[str] = None
    source_file: str = ""
    line_number: int = 0


@dataclass
class ClockGroup:
    """A set of clocks declared as asynchronous or exclusive."""
    group_type: str  # "asynchronous" or "exclusive"
    groups: List[List[str]] = field(default_factory=list)  # list of clock-name lists
    source_file: str = ""
    line_number: int = 0


# ---------------------------------------------------------------------------
# DRC Waivers
# ---------------------------------------------------------------------------

@dataclass
class DRCWaiver:
    """A design rule check waiver from a .swl file."""
    rule_id: str
    scope: str = ""       # module, signal, instance, or global
    target: str = ""      # specific module/signal name
    reason: str = ""
    suppressed: bool = True
    source_file: str = ""
    line_number: int = 0


# ---------------------------------------------------------------------------
# Block Definitions
# ---------------------------------------------------------------------------

@dataclass
class BlockDefinition:
    """A hierarchical block definition from .blk or .vblk files."""
    name: str
    block_type: str = "hierarchical"  # hierarchical, power_domain, partition
    parent: Optional[str] = None
    ports: List[str] = field(default_factory=list)
    power_domain: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    children: List[str] = field(default_factory=list)
    source_file: str = ""
    line_number: int = 0


# ---------------------------------------------------------------------------
# Register Maps
# ---------------------------------------------------------------------------

@dataclass
class RegisterField:
    """A bitfield within a register."""
    name: str
    bits: str = ""          # e.g. "7:0", "31:16", "0"
    access: str = "RW"      # RW, RO, WO, W1C, etc.
    reset_value: str = "0"
    description: str = ""


@dataclass
class RegisterEntry:
    """A single register in a register map."""
    name: str
    address: str = ""       # hex offset, e.g. "0x00"
    width: int = 32
    reset_value: str = "0x00000000"
    fields: List[RegisterField] = field(default_factory=list)
    access: str = "RW"
    description: str = ""


@dataclass
class RegisterMap:
    """Register map for a module, from .desc files."""
    module_name: str
    base_address: str = "0x0"
    registers: List[RegisterEntry] = field(default_factory=list)
    description: str = ""
    source_file: str = ""


# ---------------------------------------------------------------------------
# Synthesis Directives
# ---------------------------------------------------------------------------

@dataclass
class SynthesisDirective:
    """A synthesis directive from .tcl files."""
    directive_type: str  # attribute, dont_touch, max_fanout, set_option, keep, preserve
    target: str = ""     # module, signal, or instance name
    key: str = ""
    value: Any = None
    source_file: str = ""
    line_number: int = 0


# ---------------------------------------------------------------------------
# Unified Design Context
# ---------------------------------------------------------------------------

@dataclass
class DesignContext:
    """
    Unified container for all design constraint and configuration context.

    Built by DesignContextBuilder from .sdc, .tcl, .swl, .blk, .vblk, .desc files.
    Passed to analyzers and LLM agents for enriched analysis.
    """

    # Clock & timing (from .sdc)
    clocks: Dict[str, ClockDefinition] = field(default_factory=dict)
    timing_constraints: List[TimingConstraint] = field(default_factory=list)
    clock_groups: List[ClockGroup] = field(default_factory=list)

    # DRC waivers (from .swl)
    drc_waivers: Dict[str, List[DRCWaiver]] = field(default_factory=dict)

    # Block definitions (from .blk, .vblk)
    blocks: Dict[str, BlockDefinition] = field(default_factory=dict)

    # Register maps (from .desc)
    register_maps: Dict[str, RegisterMap] = field(default_factory=dict)

    # Synthesis directives (from .tcl)
    synthesis_directives: List[SynthesisDirective] = field(default_factory=list)

    # Discovery metadata
    discovered_files: Dict[str, List[str]] = field(default_factory=dict)
    parse_errors: List[Dict[str, str]] = field(default_factory=list)

    # -----------------------------------------------------------------------
    # Helper methods for analyzers
    # -----------------------------------------------------------------------

    @property
    def false_paths(self) -> List[TimingConstraint]:
        """All false-path constraints."""
        return [tc for tc in self.timing_constraints
                if tc.constraint_type == "false_path"]

    @property
    def multicycle_paths(self) -> List[TimingConstraint]:
        """All multicycle-path constraints."""
        return [tc for tc in self.timing_constraints
                if tc.constraint_type == "multicycle_path"]

    def get_clocks_for_cdc(self) -> Dict[str, Any]:
        """Return clock info structured for CDC analyzer consumption."""
        return {
            "definitions": {name: {
                "period_ns": clk.period_ns,
                "duty_cycle": clk.duty_cycle,
                "source_port": clk.source_port,
                "is_generated": clk.is_generated,
                "master_clock": clk.master_clock,
            } for name, clk in self.clocks.items()},
            "false_paths": [(fp.from_signal or fp.from_clock,
                             fp.to_signal or fp.to_clock)
                            for fp in self.false_paths],
            "clock_groups": [{"type": cg.group_type, "groups": cg.groups}
                             for cg in self.clock_groups],
            "clock_count": len(self.clocks),
        }

    def get_waivers_for_rule(self, prefix: str) -> List[DRCWaiver]:
        """Get all waivers whose rule_id starts with the given prefix."""
        result = []
        for rule_id, waivers in self.drc_waivers.items():
            if rule_id.startswith(prefix):
                result.extend(waivers)
        return result

    def get_false_paths_for_signals(self, sig_a: str, sig_b: str) -> List[TimingConstraint]:
        """Check if a signal pair is covered by a false-path constraint."""
        matches = []
        for fp in self.false_paths:
            from_sig = fp.from_signal or fp.from_clock or ""
            to_sig = fp.to_signal or fp.to_clock or ""
            # Match if either direction is covered
            if ((sig_a in from_sig and sig_b in to_sig) or
                    (sig_b in from_sig and sig_a in to_sig)):
                matches.append(fp)
        return matches

    def get_blocks_for_module(self, module_name: str) -> List[BlockDefinition]:
        """Get block definitions related to a module."""
        return [b for b in self.blocks.values()
                if b.name == module_name or module_name in b.children]

    def get_register_map_for_module(self, module_name: str) -> Optional[RegisterMap]:
        """Get register map for a specific module."""
        return self.register_maps.get(module_name)

    def get_synthesis_directives_for_target(self, target: str) -> List[SynthesisDirective]:
        """Get synthesis directives targeting a specific module/signal."""
        return [d for d in self.synthesis_directives if d.target == target]

    def is_signal_waived(self, rule_id: str, signal_name: str) -> bool:
        """Check if a specific signal has a waiver for a given rule."""
        waivers = self.drc_waivers.get(rule_id, [])
        return any(w.target == signal_name or w.scope == "global" for w in waivers)

    # -----------------------------------------------------------------------
    # Serialization & context formatting
    # -----------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict for report output."""
        return {
            "clocks": {name: asdict(clk) for name, clk in self.clocks.items()},
            "timing_constraints": [asdict(tc) for tc in self.timing_constraints],
            "clock_groups": [asdict(cg) for cg in self.clock_groups],
            "drc_waivers": {rule: [asdict(w) for w in waivers]
                            for rule, waivers in self.drc_waivers.items()},
            "blocks": {name: asdict(b) for name, b in self.blocks.items()},
            "register_maps": {name: asdict(rm) for name, rm in self.register_maps.items()},
            "synthesis_directives": [asdict(d) for d in self.synthesis_directives],
            "discovered_files": self.discovered_files,
            "summary": self.summary(),
        }

    def summary(self) -> Dict[str, int]:
        """Return a count summary of all discovered context."""
        return {
            "clocks": len(self.clocks),
            "timing_constraints": len(self.timing_constraints),
            "false_paths": len(self.false_paths),
            "clock_groups": len(self.clock_groups),
            "drc_waivers": sum(len(v) for v in self.drc_waivers.values()),
            "blocks": len(self.blocks),
            "register_maps": len(self.register_maps),
            "synthesis_directives": len(self.synthesis_directives),
            "constraint_files": sum(len(v) for v in self.discovered_files.values()),
        }

    def to_context_string(self, max_chars: int = 2000) -> str:
        """
        Format design context as a readable string for LLM prompt injection.

        Prioritises clock definitions and false paths (most impactful for analysis),
        then waivers, then blocks/registers, truncating to max_chars.
        """
        sections: List[str] = []

        # 1. Clock definitions (highest priority)
        if self.clocks:
            lines = ["[DESIGN CONTEXT — Clock Definitions]"]
            for name, clk in self.clocks.items():
                src = f" on port {clk.source_port}" if clk.source_port else ""
                gen = f" (generated from {clk.master_clock}, /{clk.divide_by})" if clk.is_generated else ""
                lines.append(f"  {name}: {clk.period_ns}ns ({1000/clk.period_ns:.1f} MHz){src}{gen}")
            sections.append("\n".join(lines))

        # 2. Clock groups
        if self.clock_groups:
            lines = ["[DESIGN CONTEXT — Clock Groups]"]
            for cg in self.clock_groups:
                for i, group in enumerate(cg.groups):
                    lines.append(f"  Group {i} ({cg.group_type}): {', '.join(group)}")
            sections.append("\n".join(lines))

        # 3. False paths
        if self.false_paths:
            lines = ["[DESIGN CONTEXT — False Paths]"]
            for fp in self.false_paths:
                f = fp.from_signal or fp.from_clock or "?"
                t = fp.to_signal or fp.to_clock or "?"
                lines.append(f"  {f} → {t}")
            sections.append("\n".join(lines))

        # 4. DRC waivers
        if self.drc_waivers:
            lines = ["[DESIGN CONTEXT — DRC Waivers]"]
            for rule_id, waivers in self.drc_waivers.items():
                for w in waivers:
                    lines.append(f"  {w.rule_id} [{w.scope}] {w.target}: {w.reason}")
            sections.append("\n".join(lines))

        # 5. Block definitions
        if self.blocks:
            lines = ["[DESIGN CONTEXT — Block Hierarchy]"]
            for name, blk in self.blocks.items():
                pd = f" (power: {blk.power_domain})" if blk.power_domain else ""
                lines.append(f"  {name} [{blk.block_type}]{pd}")
                if blk.children:
                    lines.append(f"    children: {', '.join(blk.children)}")
            sections.append("\n".join(lines))

        # 6. Register maps
        if self.register_maps:
            lines = ["[DESIGN CONTEXT — Register Maps]"]
            for name, rm in self.register_maps.items():
                lines.append(f"  {name} @ {rm.base_address} ({len(rm.registers)} registers)")
                for reg in rm.registers[:5]:  # limit per map
                    lines.append(f"    {reg.address} {reg.name} [{reg.width}b] {reg.access}")
                if len(rm.registers) > 5:
                    lines.append(f"    ... and {len(rm.registers) - 5} more")
            sections.append("\n".join(lines))

        # 7. Synthesis directives
        if self.synthesis_directives:
            lines = ["[DESIGN CONTEXT — Synthesis Directives]"]
            for d in self.synthesis_directives[:10]:
                lines.append(f"  {d.directive_type}: {d.target} {d.key}={d.value}")
            if len(self.synthesis_directives) > 10:
                lines.append(f"  ... and {len(self.synthesis_directives) - 10} more")
            sections.append("\n".join(lines))

        # Assemble with budget
        result = ""
        for section in sections:
            if len(result) + len(section) + 2 > max_chars:
                break
            result += section + "\n\n"

        return result.strip()
