#!/usr/bin/env python3
"""
End-to-End Test Harness for CARE Analyzers on sample_rtl/

Runs all 6 analyzers directly against sample files, bypassing the full
pipeline's heavy dependencies (networkx, rich, tqdm, etc.).

Outputs a comprehensive JSON report and prints a summary table.
"""

import os
import sys
import re
import json
import glob
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

# ── Add project root to path ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── Import analyzers (all use pure stdlib) ────────────────────────────────
from agents.analyzers.cdc_analyzer import CDCAnalyzer
from agents.analyzers.synthesis_safety_analyzer import SynthesisSafetyAnalyzer
from agents.analyzers.signal_integrity_analyzer import SignalIntegrityAnalyzer
from agents.analyzers.uninitialized_signal_analyzer import UninitializedSignalAnalyzer
from agents.analyzers.quality_analyzer import QualityAnalyzer
from agents.analyzers.complexity_analyzer import ComplexityAnalyzer


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

HDL_EXTENSIONS = {".v", ".sv", ".svh", ".vh"}

def build_file_cache(directory: str) -> List[Dict[str, Any]]:
    """Build a file_cache list from a directory of HDL files."""
    cache = []
    base = Path(directory).resolve()
    for root, dirs, files in os.walk(base):
        for fn in sorted(files):
            fp = Path(root) / fn
            if fp.suffix.lower() in HDL_EXTENSIONS:
                rel = str(fp.relative_to(base))
                source = fp.read_text(errors="replace")
                cache.append({
                    "file_name": fn,
                    "file_relative_path": rel,
                    "rel_path": rel,
                    "path": str(fp),
                    "suffix": fp.suffix.lower(),
                    "source": source,
                    "language": "systemverilog" if fp.suffix.lower() in (".sv", ".svh") else "verilog",
                    "size_bytes": fp.stat().st_size,
                    "metrics": {
                        "total_lines": source.count("\n") + 1,
                        "code_lines": sum(1 for l in source.splitlines() if l.strip() and not l.strip().startswith("//")),
                        "comment_lines": sum(1 for l in source.splitlines() if l.strip().startswith("//")),
                    },
                })
    return cache


def severity_emoji(sev: str) -> str:
    s = sev.lower()
    if s in ("critical", "error"):
        return "🔴"
    elif s in ("high", "warning"):
        return "🟠"
    elif s in ("medium", "info"):
        return "🟡"
    return "🟢"


# ═══════════════════════════════════════════════════════════════════════════
# Run all analyzers on a directory
# ═══════════════════════════════════════════════════════════════════════════

def run_all_analyzers(directory: str, label: str) -> Dict[str, Any]:
    """Run all 6 analyzers on a directory and return combined results."""
    print(f"\n{'='*72}")
    print(f"  ANALYZING: {label}")
    print(f"  Path: {directory}")
    print(f"{'='*72}")

    file_cache = build_file_cache(directory)
    print(f"  Files discovered: {len(file_cache)}")
    for f in file_cache:
        print(f"    - {f['rel_path']} ({f['metrics']['total_lines']} lines, {f['suffix']})")

    results = {
        "directory": directory,
        "label": label,
        "files": [f["rel_path"] for f in file_cache],
        "file_count": len(file_cache),
        "analyzers": {},
    }

    # ── 1. CDC Analyzer ───────────────────────────────────────────────────
    print(f"\n  [1/6] CDC Analyzer ...")
    try:
        cdc = CDCAnalyzer()
        cdc_result = cdc.analyze(file_cache)
        results["analyzers"]["cdc"] = cdc_result
        issue_count = len(cdc_result.get("issues", []))
        clock_domains = cdc_result.get("clock_domains", [])
        print(f"        Issues: {issue_count} | Clock domains: {clock_domains}")
        for iss in cdc_result.get("issues", []):
            print(f"        🟠 {iss}")
    except Exception as e:
        results["analyzers"]["cdc"] = {"error": str(e)}
        print(f"        ❌ Error: {e}")

    # ── 2. Synthesis Safety Analyzer ──────────────────────────────────────
    print(f"\n  [2/6] Synthesis Safety Analyzer ...")
    try:
        synth = SynthesisSafetyAnalyzer(codebase_path=directory)
        synth_result = synth.analyze(file_cache)
        results["analyzers"]["synthesis_safety"] = synth_result
        score = synth_result.get("score", "N/A")
        grade = synth_result.get("grade", "N/A")
        total_violations = synth_result.get("metrics", {}).get("total_violations", 0)
        print(f"        Score: {score}/100 | Grade: {grade} | Violations: {total_violations}")
        # Show top violations
        top = synth_result.get("metrics", {}).get("top_violation_types", [])
        for v in top[:10]:
            print(f"        🔸 {v['rule']}: {v['count']} occurrences")
        # Show per-file violations
        by_file = synth_result.get("metrics", {}).get("violations_by_file", {})
        for fname, violations in by_file.items():
            print(f"        📁 {fname}:")
            for viol in violations[:8]:
                sev = viol.get("severity", "info")
                line = viol.get("line", "?")
                rule = viol.get("rule", "unknown")
                msg = viol.get("message", "")
                print(f"           {severity_emoji(sev)} L{line} [{sev}] {rule}: {msg}")
    except Exception as e:
        results["analyzers"]["synthesis_safety"] = {"error": str(e)}
        print(f"        ❌ Error: {e}")

    # ── 3. Signal Integrity Analyzer ──────────────────────────────────────
    print(f"\n  [3/6] Signal Integrity Analyzer ...")
    try:
        sig = SignalIntegrityAnalyzer()
        sig_result = sig.analyze(file_cache)
        results["analyzers"]["signal_integrity"] = sig_result
        issue_count = len(sig_result.get("issues", []))
        print(f"        Issues: {issue_count}")
        for m in sig_result.get("metrics", []):
            risks = m.get("signal_integrity_risks", [])
            if risks:
                fname = m.get("file", "?")
                if isinstance(risks, int):
                    print(f"        📁 {fname}: {risks} signal integrity risk(s)")
                elif isinstance(risks, list):
                    print(f"        📁 {fname}:")
                    for r in risks[:8]:
                        print(f"           🟠 {r}")
                else:
                    print(f"        📁 {fname}: {risks}")
    except Exception as e:
        results["analyzers"]["signal_integrity"] = {"error": str(e)}
        print(f"        ❌ Error: {e}")

    # ── 4. Uninitialized Signal Analyzer ──────────────────────────────────
    print(f"\n  [4/6] Uninitialized Signal Analyzer ...")
    try:
        uninit = UninitializedSignalAnalyzer()
        uninit_result = uninit.analyze(file_cache)
        results["analyzers"]["uninitialized_signals"] = uninit_result
        issue_count = len(uninit_result.get("issues", []))
        print(f"        Issues: {issue_count}")
        for m in uninit_result.get("metrics", []):
            risks = m.get("uninitialized_risks", [])
            if risks:
                fname = m.get("file", "?")
                if isinstance(risks, int):
                    print(f"        📁 {fname}: {risks} uninitialized risk(s)")
                elif isinstance(risks, list):
                    print(f"        📁 {fname}:")
                    for r in risks[:8]:
                        print(f"           🟡 {r}")
                else:
                    print(f"        📁 {fname}: {risks}")
    except Exception as e:
        results["analyzers"]["uninitialized_signals"] = {"error": str(e)}
        print(f"        ❌ Error: {e}")

    # ── 5. Quality Analyzer ───────────────────────────────────────────────
    print(f"\n  [5/6] Quality Analyzer ...")
    try:
        qual = QualityAnalyzer(codebase_path=directory)
        qual_result = qual.analyze(file_cache)
        results["analyzers"]["quality"] = qual_result
        score = qual_result.get("score", "N/A")
        grade = qual_result.get("grade", "N/A")
        total_violations = qual_result.get("metrics", {}).get("total_violations", 0)
        print(f"        Score: {score}/100 | Grade: {grade} | Violations: {total_violations}")
        for v in qual_result.get("violations", [])[:10]:
            sev = v.get("severity", "info")
            line = v.get("line", "?")
            rule = v.get("rule", "unknown")
            fname = v.get("file", "?")
            msg = v.get("message", "")
            print(f"        {severity_emoji(sev)} {fname}:L{line} [{sev}] {rule}: {msg}")
    except Exception as e:
        results["analyzers"]["quality"] = {"error": str(e)}
        print(f"        ❌ Error: {e}")

    # ── 6. Complexity Analyzer ────────────────────────────────────────────
    print(f"\n  [6/6] Complexity Analyzer ...")
    try:
        comp = ComplexityAnalyzer(codebase_path=directory)
        comp_result = comp.analyze(file_cache)
        results["analyzers"]["complexity"] = comp_result
        score = comp_result.get("score", "N/A")
        grade = comp_result.get("grade", "N/A")
        summary = comp_result.get("metrics", {}).get("summary", {})
        print(f"        Score: {score}/100 | Grade: {grade}")
        print(f"        Total blocks: {summary.get('total_blocks', 0)} | "
              f"Avg CC: {summary.get('average_cc', 0):.1f} | "
              f"Max CC: {summary.get('max_cc', 0)} | "
              f"Max nesting: {summary.get('max_nesting', 0)}")
        for iss in comp_result.get("issues", [])[:5]:
            print(f"        🟡 {iss}")
    except Exception as e:
        results["analyzers"]["complexity"] = {"error": str(e)}
        print(f"        ❌ Error: {e}")

    return results


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    sample_dir = PROJECT_ROOT / "sample_rtl"
    out_dir = PROJECT_ROOT / "out" / "e2e_test"
    os.makedirs(out_dir, exist_ok=True)

    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║         CARE — End-to-End Analyzer Test Suite                       ║")
    print("║         Running all 6 analyzers on sample_rtl/                      ║")
    print(f"║         {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):>42s}          ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")

    all_results = {}

    # Run on each category
    for category in ["buggy", "mixed", "good"]:
        cat_dir = sample_dir / category
        if cat_dir.exists():
            all_results[category] = run_all_analyzers(str(cat_dir), f"sample_rtl/{category}")

    # ── Summary Table ─────────────────────────────────────────────────────
    print("\n\n" + "=" * 72)
    print("  SUMMARY — Analyzer Results Across Categories")
    print("=" * 72)
    print(f"\n  {'Category':<12} {'Analyzer':<26} {'Score':>6} {'Grade':>6} {'Issues/Violations':>18}")
    print(f"  {'-'*12} {'-'*26} {'-'*6} {'-'*6} {'-'*18}")

    for category, result in all_results.items():
        analyzers = result.get("analyzers", {})
        first = True
        for aname, adata in analyzers.items():
            if isinstance(adata, dict) and "error" not in adata:
                score = adata.get("score", "-")
                grade = adata.get("grade", "-")
                issues = len(adata.get("issues", []))
                metrics = adata.get("metrics", {})
                if isinstance(metrics, dict):
                    violations = metrics.get("total_violations", issues)
                elif isinstance(metrics, list):
                    violations = issues
                else:
                    violations = issues
                cat_label = category if first else ""
                print(f"  {cat_label:<12} {aname:<26} {str(score):>6} {str(grade):>6} {violations:>18}")
                first = False
        print()

    # ── Save JSON report ──────────────────────────────────────────────────
    report = {
        "test_run": datetime.now().isoformat(),
        "sample_dir": str(sample_dir),
        "results": all_results,
    }
    report_path = out_dir / "e2e_test_results.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n  Full report saved: {report_path}")

    # ── Return success / failure ──────────────────────────────────────────
    # Check that buggy files have significantly more issues than good files
    buggy_issues = 0
    good_issues = 0
    for aname, adata in all_results.get("buggy", {}).get("analyzers", {}).items():
        if isinstance(adata, dict):
            buggy_issues += len(adata.get("issues", []))
            m = adata.get("metrics", {})
            if isinstance(m, dict):
                buggy_issues += m.get("total_violations", 0)
    for aname, adata in all_results.get("good", {}).get("analyzers", {}).items():
        if isinstance(adata, dict):
            good_issues += len(adata.get("issues", []))
            m = adata.get("metrics", {})
            if isinstance(m, dict):
                good_issues += m.get("total_violations", 0)

    print(f"\n  Buggy total issues/violations : {buggy_issues}")
    print(f"  Good total issues/violations  : {good_issues}")

    if buggy_issues > good_issues:
        print(f"\n  ✅ PASS — Buggy files flagged more issues ({buggy_issues}) than good files ({good_issues})")
    else:
        print(f"\n  ❌ FAIL — Expected buggy > good issues, got buggy={buggy_issues}, good={good_issues}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
