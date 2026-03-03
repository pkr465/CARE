"""
Design context builder — discovers and parses constraint/configuration files.

Supports:
  .sdc  — Synopsys Design Constraints (clocks, timing, false paths)
  .tcl  — Tool Command Language (synthesis directives)
  .swl  — PLD Rule Check waivers (DRC suppressions)
  .blk  — Block-level descriptors (hierarchy, power domains)
  .vblk — Virtual block descriptors (partitions, power intent)
  .desc — Design descriptors (register maps, IP parameters)

All parsers use pure stdlib (re, typing, pathlib) — no external dependencies.
"""

import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Any, Optional

from agents.context.design_context import (
    DesignContext,
    ClockDefinition,
    TimingConstraint,
    ClockGroup,
    DRCWaiver,
    BlockDefinition,
    RegisterMap,
    RegisterEntry,
    RegisterField,
    SynthesisDirective,
)

logger = logging.getLogger(__name__)


# ===========================================================================
# SDC Parser
# ===========================================================================

class SDCParser:
    """
    Parses Synopsys Design Constraint (.sdc) files.

    Extracts:
      - create_clock / create_generated_clock
      - set_false_path
      - set_multicycle_path
      - set_input_delay / set_output_delay
      - set_max_delay / set_min_delay
      - set_clock_groups
    """

    # -- Pre-join line continuations, strip comments --
    _CONTINUATION = re.compile(r"\\\s*\n")
    _COMMENT = re.compile(r"#.*$", re.MULTILINE)

    # -- SDC command patterns --
    # create_clock -period 10.0 -name clk_main -waveform {0 5} [get_ports clk]
    _CREATE_CLOCK = re.compile(
        r"create_clock\b"
        r"(?:\s+-period\s+(\d+(?:\.\d+)?))"      # (1) period
        r"(?:\s+-name\s+(\w+))?"                   # (2) name
        r"(?:\s+-waveform\s+\{([^}]+)\})?"         # (3) waveform
        r"(?:\s+\[get_ports\s+\{?(\w+)\}?\])?"     # (4) port
        r"(?:[ \t]+(\w+))?",                        # (5) bare signal name (same line only)
        re.IGNORECASE,
    )

    # create_generated_clock -source [get_ports clk] -divide_by 2 -name clk_div2
    _CREATE_GEN_CLOCK = re.compile(
        r"create_generated_clock\b"
        r"(?:\s+-source\s+\[get_(?:ports|pins)\s+\{?(\w+)\}?\])?"  # (1) source
        r"(?:\s+-divide_by\s+(\d+))?"                                # (2) divide
        r"(?:\s+-multiply_by\s+(\d+))?"                              # (3) multiply
        r"(?:\s+-name\s+(\w+))?",                                    # (4) name
        re.IGNORECASE,
    )

    # set_false_path -from [get_clocks clk_a] -to [get_clocks clk_b]
    _FALSE_PATH = re.compile(
        r"set_false_path\b"
        r"(?:\s+-from\s+\[get_(?:clocks|pins|cells|ports)\s+\{?([^]\}]+)\}?\])?"  # (1) from
        r"(?:\s+-to\s+\[get_(?:clocks|pins|cells|ports)\s+\{?([^]\}]+)\}?\])?",    # (2) to
        re.IGNORECASE,
    )

    # set_multicycle_path 2 -from [get_clocks clk_a] -to [get_clocks clk_b]
    _MULTICYCLE = re.compile(
        r"set_multicycle_path\s+(\d+)"                                              # (1) cycles
        r"(?:\s+-(?:setup|hold))?"
        r"(?:\s+-from\s+\[get_(?:clocks|pins|cells|ports)\s+\{?([^]\}]+)\}?\])?"  # (2) from
        r"(?:\s+-to\s+\[get_(?:clocks|pins|cells|ports)\s+\{?([^]\}]+)\}?\])?",    # (3) to
        re.IGNORECASE,
    )

    # set_input_delay 2.5 -clock clk_main [get_ports data_in]
    _INPUT_DELAY = re.compile(
        r"set_input_delay\s+(-?\d+(?:\.\d+)?)"                    # (1) delay
        r"(?:\s+-clock\s+(\w+))?"                                   # (2) clock
        r"(?:\s+\[get_ports\s+\{?([^]\}]+)\}?\])?",                # (3) ports
        re.IGNORECASE,
    )

    # set_output_delay 1.8 -clock clk_main [get_ports data_out]
    _OUTPUT_DELAY = re.compile(
        r"set_output_delay\s+(-?\d+(?:\.\d+)?)"
        r"(?:\s+-clock\s+(\w+))?"
        r"(?:\s+\[get_ports\s+\{?([^]\}]+)\}?\])?",
        re.IGNORECASE,
    )

    # set_max_delay / set_min_delay
    _MAX_MIN_DELAY = re.compile(
        r"set_(max|min)_delay\s+(-?\d+(?:\.\d+)?)"                # (1) type, (2) delay
        r"(?:\s+-from\s+\[get_(?:clocks|pins|cells|ports)\s+\{?([^]\}]+)\}?\])?"  # (3) from
        r"(?:\s+-to\s+\[get_(?:clocks|pins|cells|ports)\s+\{?([^]\}]+)\}?\])?",    # (4) to
        re.IGNORECASE,
    )

    # set_clock_groups -asynchronous -group {clk1} -group {clk2 clk3}
    _CLOCK_GROUPS = re.compile(
        r"set_clock_groups\b\s+-(asynchronous|exclusive)"          # (1) type
        r"((?:\s+-group\s+\{[^}]+\})+)",                          # (2) all groups
        re.IGNORECASE,
    )
    _GROUP_EXTRACT = re.compile(r"-group\s+\{([^}]+)\}")

    def parse(self, file_path: Path) -> Dict[str, Any]:
        """Parse an SDC file and return structured constraint data."""
        raw = file_path.read_text(encoding="utf-8", errors="ignore")
        # Pre-process: join continuations, strip comments
        content = self._CONTINUATION.sub(" ", raw)
        content = self._COMMENT.sub("", content)
        src = str(file_path)

        result: Dict[str, Any] = {
            "clocks": {},
            "timing_constraints": [],
            "clock_groups": [],
        }

        # --- create_clock ---
        for m in self._CREATE_CLOCK.finditer(content):
            period_str, name, waveform_str, port, bare = m.groups()
            if not period_str:
                continue
            period = float(period_str)
            clk_name = name or port or bare or f"clk_{id(m)}"
            source_port = port or bare
            waveform = None
            duty = 0.5
            if waveform_str:
                parts = waveform_str.strip().split()
                if len(parts) == 2:
                    try:
                        rise, fall = float(parts[0]), float(parts[1])
                        waveform = (rise, fall)
                        duty = (fall - rise) / period if period > 0 else 0.5
                    except ValueError:
                        pass

            result["clocks"][clk_name] = ClockDefinition(
                name=clk_name,
                period_ns=period,
                duty_cycle=duty,
                waveform=waveform,
                source_port=source_port,
                source_file=src,
                line_number=raw[:m.start()].count("\n") + 1,
            )

        # --- create_generated_clock ---
        for m in self._CREATE_GEN_CLOCK.finditer(content):
            source, divide, multiply, name = m.groups()
            if not name:
                continue
            master_period = 10.0  # default fallback
            if source and source in result["clocks"]:
                master_period = result["clocks"][source].period_ns
            div = int(divide) if divide else 1
            mul = int(multiply) if multiply else 1
            gen_period = master_period * div / mul

            result["clocks"][name] = ClockDefinition(
                name=name,
                period_ns=gen_period,
                is_generated=True,
                master_clock=source,
                divide_by=int(divide) if divide else None,
                multiply_by=int(multiply) if multiply else None,
                source_file=src,
                line_number=raw[:m.start()].count("\n") + 1,
            )

        # --- set_false_path ---
        for m in self._FALSE_PATH.finditer(content):
            from_sig, to_sig = m.groups()
            if from_sig or to_sig:
                result["timing_constraints"].append(TimingConstraint(
                    constraint_type="false_path",
                    from_signal=from_sig.strip() if from_sig else None,
                    to_signal=to_sig.strip() if to_sig else None,
                    source_file=src,
                    line_number=raw[:m.start()].count("\n") + 1,
                ))

        # --- set_multicycle_path ---
        for m in self._MULTICYCLE.finditer(content):
            cycles, from_sig, to_sig = m.groups()
            result["timing_constraints"].append(TimingConstraint(
                constraint_type="multicycle_path",
                from_signal=from_sig.strip() if from_sig else None,
                to_signal=to_sig.strip() if to_sig else None,
                cycles=int(cycles),
                source_file=src,
                line_number=raw[:m.start()].count("\n") + 1,
            ))

        # --- set_input_delay ---
        for m in self._INPUT_DELAY.finditer(content):
            delay, clock, ports = m.groups()
            result["timing_constraints"].append(TimingConstraint(
                constraint_type="input_delay",
                to_signal=ports.strip() if ports else None,
                clock_ref=clock,
                delay_ns=float(delay),
                source_file=src,
                line_number=raw[:m.start()].count("\n") + 1,
            ))

        # --- set_output_delay ---
        for m in self._OUTPUT_DELAY.finditer(content):
            delay, clock, ports = m.groups()
            result["timing_constraints"].append(TimingConstraint(
                constraint_type="output_delay",
                from_signal=ports.strip() if ports else None,
                clock_ref=clock,
                delay_ns=float(delay),
                source_file=src,
                line_number=raw[:m.start()].count("\n") + 1,
            ))

        # --- set_max_delay / set_min_delay ---
        for m in self._MAX_MIN_DELAY.finditer(content):
            kind, delay, from_sig, to_sig = m.groups()
            result["timing_constraints"].append(TimingConstraint(
                constraint_type=f"{kind}_delay",
                from_signal=from_sig.strip() if from_sig else None,
                to_signal=to_sig.strip() if to_sig else None,
                delay_ns=float(delay),
                source_file=src,
                line_number=raw[:m.start()].count("\n") + 1,
            ))

        # --- set_clock_groups ---
        for m in self._CLOCK_GROUPS.finditer(content):
            group_type, groups_str = m.groups()
            groups = []
            for gm in self._GROUP_EXTRACT.finditer(groups_str):
                clk_names = [c.strip() for c in gm.group(1).split()]
                if clk_names:
                    groups.append(clk_names)
            if groups:
                result["clock_groups"].append(ClockGroup(
                    group_type=group_type.lower(),
                    groups=groups,
                    source_file=src,
                    line_number=raw[:m.start()].count("\n") + 1,
                ))

        return result


# ===========================================================================
# TCL Parser
# ===========================================================================

class TCLParser:
    """
    Parses Tool Command Language (.tcl) scripts for synthesis directives.

    Extracts:
      - set_dont_touch, set_attribute, set_max_fanout
      - set variable assignments (synthesis options)
      - read_sdc references
    """

    _DONT_TOUCH = re.compile(
        r"set_dont_touch\s+\[get_(?:cells|nets|pins)\s+\{?(\w+)\}?\]",
        re.IGNORECASE,
    )
    _MAX_FANOUT = re.compile(
        r"set_max_fanout\s+(\d+)\s+\[get_(?:ports|cells|nets)\s+\{?(\w+)\}?\]",
        re.IGNORECASE,
    )
    _SET_ATTRIBUTE = re.compile(
        r"set_attribute\s+\[get_(?:cells|nets|ports|pins)\s+\{?(\w+)\}?\]\s+"
        r"(\w+)\s+(\S+)",
        re.IGNORECASE,
    )
    _SYNTH_SET = re.compile(
        r"^set\s+(\w+)\s+(.+?)\s*$",
        re.MULTILINE,
    )
    _KEEP = re.compile(
        r"set_attribute\s+.*?\bkeep\b\s+true",
        re.IGNORECASE,
    )
    _COMMENT = re.compile(r"#.*$", re.MULTILINE)
    _CONTINUATION = re.compile(r"\\\s*\n")

    def parse(self, file_path: Path) -> Dict[str, Any]:
        """Parse TCL file for synthesis-relevant directives."""
        raw = file_path.read_text(encoding="utf-8", errors="ignore")
        content = self._CONTINUATION.sub(" ", raw)
        content = self._COMMENT.sub("", content)
        src = str(file_path)

        result: Dict[str, Any] = {"synthesis_directives": []}

        # dont_touch
        for m in self._DONT_TOUCH.finditer(content):
            result["synthesis_directives"].append(SynthesisDirective(
                directive_type="dont_touch",
                target=m.group(1),
                key="dont_touch",
                value=True,
                source_file=src,
                line_number=raw[:m.start()].count("\n") + 1,
            ))

        # max_fanout
        for m in self._MAX_FANOUT.finditer(content):
            result["synthesis_directives"].append(SynthesisDirective(
                directive_type="max_fanout",
                target=m.group(2),
                key="max_fanout",
                value=int(m.group(1)),
                source_file=src,
                line_number=raw[:m.start()].count("\n") + 1,
            ))

        # set_attribute
        for m in self._SET_ATTRIBUTE.finditer(content):
            target, attr, value = m.groups()
            result["synthesis_directives"].append(SynthesisDirective(
                directive_type="attribute",
                target=target,
                key=attr,
                value=value,
                source_file=src,
                line_number=raw[:m.start()].count("\n") + 1,
            ))

        # Synthesis-relevant set variables (filter out trivial ones)
        _SYNTH_KEYWORDS = {
            "target_library", "link_library", "search_path",
            "compile_ultra", "timing_driven", "area_driven",
            "max_area", "max_dynamic_power", "clock_gating_enable",
        }
        for m in self._SYNTH_SET.finditer(content):
            var_name, var_value = m.groups()
            if var_name.lower() in _SYNTH_KEYWORDS or var_name.startswith("synth_"):
                result["synthesis_directives"].append(SynthesisDirective(
                    directive_type="set_option",
                    target="synthesis",
                    key=var_name,
                    value=var_value.strip().strip('"'),
                    source_file=src,
                    line_number=raw[:m.start()].count("\n") + 1,
                ))

        return result


# ===========================================================================
# SWL Parser (DRC Waivers)
# ===========================================================================

class SWLParser:
    """
    Parses PLD Rule Check waiver files (.swl).

    Supports two formats:
      1. Pipe-delimited: rule_id | scope | target | reason
      2. Key-value:      RULE: HDL-DRC-001; SCOPE: module_foo; WAIVE: true; REASON: ...
    """

    _PIPE_LINE = re.compile(
        r"^\s*([A-Za-z0-9_-]+)\s*\|\s*([A-Za-z0-9_*]+)\s*\|\s*([A-Za-z0-9_*]*)\s*\|?\s*(.*?)\s*$"
    )
    _KV_RULE = re.compile(r"RULE:\s*([A-Za-z0-9_-]+)", re.IGNORECASE)
    _KV_SCOPE = re.compile(r"SCOPE:\s*(\S+)", re.IGNORECASE)
    _KV_TARGET = re.compile(r"TARGET:\s*(\S+)", re.IGNORECASE)
    _KV_REASON = re.compile(r"REASON:\s*(.+?)(?:;|$)", re.IGNORECASE)

    def parse(self, file_path: Path) -> Dict[str, Any]:
        """Parse waiver file."""
        raw = file_path.read_text(encoding="utf-8", errors="ignore")
        src = str(file_path)
        result: Dict[str, Any] = {"drc_waivers": {}}

        for line_num, line in enumerate(raw.split("\n"), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                continue

            waiver = None

            # Try pipe-delimited format
            pm = self._PIPE_LINE.match(stripped)
            if pm:
                rule_id, scope, target, reason = pm.groups()
                waiver = DRCWaiver(
                    rule_id=rule_id.strip(),
                    scope=scope.strip(),
                    target=target.strip() if target else "",
                    reason=reason.strip(),
                    source_file=src,
                    line_number=line_num,
                )
            else:
                # Try key-value format
                rm = self._KV_RULE.search(stripped)
                if rm:
                    rule_id = rm.group(1)
                    scope_m = self._KV_SCOPE.search(stripped)
                    target_m = self._KV_TARGET.search(stripped)
                    reason_m = self._KV_REASON.search(stripped)
                    waiver = DRCWaiver(
                        rule_id=rule_id,
                        scope=scope_m.group(1) if scope_m else "global",
                        target=target_m.group(1) if target_m else "",
                        reason=reason_m.group(1).strip() if reason_m else "",
                        source_file=src,
                        line_number=line_num,
                    )

            if waiver:
                if waiver.rule_id not in result["drc_waivers"]:
                    result["drc_waivers"][waiver.rule_id] = []
                result["drc_waivers"][waiver.rule_id].append(waiver)

        return result


# ===========================================================================
# BLK Parser (Block Definitions)
# ===========================================================================

class BLKParser:
    """
    Parses block descriptor (.blk) files.

    Supports a simple hierarchical format:
      block <name> {
        type: hierarchical|power_domain|partition
        parent: <parent_block>
        power_domain: <domain>
        ports: <port1>, <port2>, ...
        children: <child1>, <child2>, ...
      }

    Also handles flat key-value lines for simpler .blk formats.
    """

    _BLOCK_START = re.compile(r"block\s+(\w+)\s*\{")
    _BLOCK_END = re.compile(r"^\s*\}")
    _KV = re.compile(r"^\s*(\w+)\s*:\s*(.+?)\s*$")

    def parse(self, file_path: Path) -> Dict[str, Any]:
        """Parse block descriptor file."""
        raw = file_path.read_text(encoding="utf-8", errors="ignore")
        src = str(file_path)
        result: Dict[str, Any] = {"blocks": {}}

        lines = raw.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Skip comments and blanks
            if not line or line.startswith("#") or line.startswith("//"):
                i += 1
                continue

            # Block start
            bm = self._BLOCK_START.match(line)
            if bm:
                block_name = bm.group(1)
                block = BlockDefinition(
                    name=block_name,
                    source_file=src,
                    line_number=i + 1,
                )
                i += 1
                # Read block body
                while i < len(lines):
                    bline = lines[i].strip()
                    if self._BLOCK_END.match(bline):
                        i += 1
                        break
                    kv = self._KV.match(bline)
                    if kv:
                        key, value = kv.group(1).lower(), kv.group(2)
                        if key == "type":
                            block.block_type = value.strip()
                        elif key == "parent":
                            block.parent = value.strip()
                        elif key == "power_domain":
                            block.power_domain = value.strip()
                        elif key == "ports":
                            block.ports = [p.strip() for p in value.split(",") if p.strip()]
                        elif key == "children":
                            block.children = [c.strip() for c in value.split(",") if c.strip()]
                        else:
                            block.attributes[key] = value.strip()
                    i += 1
                result["blocks"][block_name] = block
            else:
                # Flat key-value fallback (simple .blk without braces)
                kv = self._KV.match(line)
                if kv:
                    key, value = kv.group(1).lower(), kv.group(2).strip()
                    if key == "block":
                        result["blocks"][value] = BlockDefinition(
                            name=value,
                            source_file=src,
                            line_number=i + 1,
                        )
                i += 1

        return result


# ===========================================================================
# VBLK Parser (Virtual Block / Partition)
# ===========================================================================

class VBLKParser:
    """
    Parses virtual block descriptor (.vblk) files.

    Uses same format as BLKParser but defaults to partition type
    and extracts power-intent annotations.
    """

    _BLOCK_START = re.compile(r"(?:vblock|partition|domain)\s+(\w+)\s*\{", re.IGNORECASE)
    _BLOCK_END = re.compile(r"^\s*\}")
    _KV = re.compile(r"^\s*(\w+)\s*:\s*(.+?)\s*$")

    def parse(self, file_path: Path) -> Dict[str, Any]:
        """Parse virtual block file."""
        raw = file_path.read_text(encoding="utf-8", errors="ignore")
        src = str(file_path)
        result: Dict[str, Any] = {"blocks": {}}

        lines = raw.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line or line.startswith("#") or line.startswith("//"):
                i += 1
                continue

            bm = self._BLOCK_START.match(line)
            if bm:
                block_name = bm.group(1)
                block = BlockDefinition(
                    name=block_name,
                    block_type="partition",
                    source_file=src,
                    line_number=i + 1,
                )
                i += 1
                while i < len(lines):
                    bline = lines[i].strip()
                    if self._BLOCK_END.match(bline):
                        i += 1
                        break
                    kv = self._KV.match(bline)
                    if kv:
                        key, value = kv.group(1).lower(), kv.group(2).strip()
                        if key == "power_domain":
                            block.power_domain = value
                            block.block_type = "power_domain"
                        elif key == "parent":
                            block.parent = value
                        elif key == "children":
                            block.children = [c.strip() for c in value.split(",") if c.strip()]
                        elif key == "ports":
                            block.ports = [p.strip() for p in value.split(",") if p.strip()]
                        else:
                            block.attributes[key] = value
                    i += 1
                result["blocks"][block_name] = block
            else:
                i += 1

        return result


# ===========================================================================
# DESC Parser (Register Maps / IP Descriptors)
# ===========================================================================

class DESCParser:
    """
    Parses design descriptor (.desc) files.

    Supports:
      - Register map tables (# header sections, address/name/width/reset/fields)
      - IP interface descriptions
      - Module parameter documentation

    Format example:
      # module: uart_tx
      # base_address: 0x40000000
      0x00 | TX_DATA   | 8  | 0x00 | RW | Transmit data register
      0x04 | TX_STATUS | 8  | 0x00 | RO | Status: [0]=busy, [1]=done
      0x08 | TX_CTRL   | 8  | 0x01 | RW | Control: [0]=enable, [7:1]=baud_div
    """

    _MODULE_HEADER = re.compile(r"#\s*module:\s*(\w+)", re.IGNORECASE)
    _BASE_ADDR = re.compile(r"#\s*base_address:\s*(0x[0-9a-fA-F]+|\d+)", re.IGNORECASE)
    _DESCRIPTION = re.compile(r"#\s*description:\s*(.+)", re.IGNORECASE)
    _REG_LINE = re.compile(
        r"^\s*(0x[0-9a-fA-F]+|\d+)\s*\|\s*(\w+)\s*\|\s*(\d+)\s*\|\s*"
        r"(0x[0-9a-fA-F]+|\d+)\s*\|\s*(\w+)\s*\|\s*(.*?)\s*$"
    )
    _FIELD_PATTERN = re.compile(r"\[(\d+(?::\d+)?)\]=?(\w+)?")

    def parse(self, file_path: Path) -> Dict[str, Any]:
        """Parse descriptor file."""
        raw = file_path.read_text(encoding="utf-8", errors="ignore")
        src = str(file_path)
        result: Dict[str, Any] = {"registers": {}}

        current_module: Optional[str] = None
        current_map: Optional[RegisterMap] = None
        base_addr = "0x0"
        desc = ""

        for line_num, line in enumerate(raw.split("\n"), 1):
            stripped = line.strip()
            if not stripped:
                continue

            # Module header
            mm = self._MODULE_HEADER.match(stripped)
            if mm:
                # Save previous map if any
                if current_module and current_map:
                    result["registers"][current_module] = current_map

                current_module = mm.group(1)
                base_addr = "0x0"
                desc = ""
                current_map = None
                continue

            # Base address
            bm = self._BASE_ADDR.match(stripped)
            if bm:
                base_addr = bm.group(1)
                continue

            # Description
            dm = self._DESCRIPTION.match(stripped)
            if dm:
                desc = dm.group(1).strip()
                continue

            # Skip other comments
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            # Register line
            rm = self._REG_LINE.match(stripped)
            if rm:
                addr, name, width, reset, access, reg_desc = rm.groups()

                if not current_map:
                    current_map = RegisterMap(
                        module_name=current_module or file_path.stem,
                        base_address=base_addr,
                        description=desc,
                        source_file=src,
                    )

                # Parse field descriptions from reg_desc
                fields = []
                for fm in self._FIELD_PATTERN.finditer(reg_desc):
                    bits, field_name = fm.groups()
                    fields.append(RegisterField(
                        name=field_name or f"field_{bits}",
                        bits=bits,
                        access=access,
                    ))

                current_map.registers.append(RegisterEntry(
                    name=name,
                    address=addr,
                    width=int(width),
                    reset_value=reset,
                    access=access,
                    description=reg_desc.strip(),
                    fields=fields,
                ))

        # Save last map
        if current_module and current_map:
            result["registers"][current_module] = current_map
        elif current_map:
            mod_name = file_path.stem
            result["registers"][mod_name] = current_map

        return result


# ===========================================================================
# Design Context Builder (Orchestrator)
# ===========================================================================

class DesignContextBuilder:
    """
    Discovers and parses all design constraint files in a codebase.
    Produces a unified DesignContext object.
    """

    # Default discovery glob patterns per file type
    DEFAULT_PATTERNS: Dict[str, List[str]] = {
        ".sdc": ["**/*.sdc"],
        ".tcl": ["**/*.tcl"],
        ".swl": ["**/pldrc/**/*.swl", "**/waivers/**/*.swl", "**/*.swl"],
        ".blk": ["**/*.blk"],
        ".vblk": ["**/*.vblk"],
        ".desc": ["**/*.desc"],
    }

    # Directories to always skip
    DEFAULT_EXCLUDE_DIRS = {
        ".git", ".svn", ".hg", ".venv", "venv", "node_modules",
        "__pycache__", ".pytest_cache", "vendor", "third_party",
        ".Xil", "xsim.dir",
    }

    def __init__(self, codebase_path: str,
                 config: Optional[Dict[str, Any]] = None):
        self.codebase_path = Path(codebase_path).resolve()
        self.config = config or {}
        self.design_context = DesignContext()

        # Parsers keyed by extension
        self._parsers: Dict[str, Any] = {
            ".sdc": SDCParser(),
            ".tcl": TCLParser(),
            ".swl": SWLParser(),
            ".blk": BLKParser(),
            ".vblk": VBLKParser(),
            ".desc": DESCParser(),
        }

        # Merge config patterns with defaults
        self._patterns = dict(self.DEFAULT_PATTERNS)
        discovery_cfg = self.config.get("discovery", {})
        for ext in self._patterns:
            cfg_key = f"{ext.lstrip('.')}_patterns"
            if cfg_key in discovery_cfg:
                self._patterns[ext] = discovery_cfg[cfg_key]

        # Exclude patterns from config
        self._exclude_patterns = self.config.get("exclude_patterns", [])

    def discover_files(self) -> Dict[str, List[Path]]:
        """
        Scan codebase for constraint files matching configured patterns.
        Returns dict: extension -> [file_paths]
        """
        discovered: Dict[str, List[Path]] = defaultdict(list)

        if not self.codebase_path.is_dir():
            logger.warning(f"Codebase path does not exist: {self.codebase_path}")
            return discovered

        for ext, patterns in self._patterns.items():
            seen_paths = set()
            for pattern in patterns:
                glob_pattern = pattern.removeprefix("**/") if pattern.startswith("**/") else pattern
                for file_path in self.codebase_path.rglob(glob_pattern):
                    if not file_path.is_file():
                        continue
                    if file_path.resolve() in seen_paths:
                        continue
                    if self._is_excluded(file_path):
                        continue
                    seen_paths.add(file_path.resolve())
                    discovered[ext].append(file_path)

        # Store in context
        self.design_context.discovered_files = {
            ext: [str(p) for p in paths]
            for ext, paths in discovered.items()
        }

        return discovered

    def _is_excluded(self, file_path: Path) -> bool:
        """Check if a file should be excluded based on directory and pattern rules."""
        parts = file_path.parts
        for part in parts:
            if part in self.DEFAULT_EXCLUDE_DIRS:
                return True

        rel = str(file_path.relative_to(self.codebase_path))
        for pattern in self._exclude_patterns:
            if re.match(pattern.replace("**", ".*").replace("*", "[^/]*"), rel):
                return True

        return False

    def build_context(self) -> DesignContext:
        """
        Main entry point: discover all constraint files, parse them,
        and return a unified DesignContext.
        """
        discovered = self.discover_files()

        total_parsed = 0
        for ext, files in discovered.items():
            parser = self._parsers.get(ext)
            if not parser:
                logger.warning(f"No parser available for {ext} files")
                continue

            for file_path in files:
                try:
                    parsed = parser.parse(file_path)
                    self._merge_results(parsed)
                    total_parsed += 1
                except Exception as e:
                    logger.error(f"Failed to parse {file_path}: {e}")
                    self.design_context.parse_errors.append({
                        "file": str(file_path),
                        "error": str(e),
                    })

        logger.info(
            f"Design context built: {total_parsed} files parsed — "
            f"{len(self.design_context.clocks)} clocks, "
            f"{len(self.design_context.timing_constraints)} constraints, "
            f"{sum(len(v) for v in self.design_context.drc_waivers.values())} waivers, "
            f"{len(self.design_context.blocks)} blocks, "
            f"{len(self.design_context.register_maps)} register maps, "
            f"{len(self.design_context.synthesis_directives)} directives"
        )

        return self.design_context

    def _merge_results(self, parsed: Dict[str, Any]) -> None:
        """Merge parser output into the unified DesignContext."""
        if "clocks" in parsed:
            self.design_context.clocks.update(parsed["clocks"])

        if "timing_constraints" in parsed:
            self.design_context.timing_constraints.extend(parsed["timing_constraints"])

        if "clock_groups" in parsed:
            self.design_context.clock_groups.extend(parsed["clock_groups"])

        if "drc_waivers" in parsed:
            for rule_id, waivers in parsed["drc_waivers"].items():
                if rule_id not in self.design_context.drc_waivers:
                    self.design_context.drc_waivers[rule_id] = []
                self.design_context.drc_waivers[rule_id].extend(waivers)

        if "blocks" in parsed:
            self.design_context.blocks.update(parsed["blocks"])

        if "registers" in parsed:
            self.design_context.register_maps.update(parsed["registers"])

        if "synthesis_directives" in parsed:
            self.design_context.synthesis_directives.extend(parsed["synthesis_directives"])
