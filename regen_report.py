#!/usr/bin/env python3
"""
Regenerate HTML report from an existing evaluation JSON.
Usage:
    python regen_report.py                          # uses latest JSON
    python regen_report.py evaluation_results/x.json

Works with both old JSONs (no findings embedded) and new ones (findings embedded).
Old JSONs will show gap descriptions and cross-check status but no page ranges or distances.
"""

import json
import sys
from pathlib import Path

WORKSPACE   = Path(__file__).parent
RESULTS_DIR = WORKSPACE / "evaluation_results"

def main():
    if len(sys.argv) > 1:
        json_path = Path(sys.argv[1])
    else:
        jsons = sorted(RESULTS_DIR.glob("*.json"))
        if not jsons:
            print("No JSON files found in evaluation_results/")
            sys.exit(1)
        json_path = jsons[-1]

    print(f"Loading: {json_path.name}")
    with open(json_path, encoding="utf-8") as f:
        result = json.load(f)

    # Use embedded findings if present (new format), otherwise empty stubs
    findings = result.get("findings", [])
    if not findings:
        print("  Note: findings not embedded in this JSON (old format). "
              "Page ranges and distances will be unavailable.")
        # Create stubs so get_finding() doesn't crash
        n = max((v.get("id", 0) for v in result.get("verdicts", []) if isinstance(v, dict)), default=0)
        findings = [{}] * n

    # Import and call the report generator
    import rag_evaluator
    stamp = json_path.stem.split("_")[-2] + "_" + json_path.stem.split("_")[-1]
    pdf_path = WORKSPACE / "test_transactions" / result["document"]

    report_path = rag_evaluator._generate_report(result, findings, stamp, pdf_path)
    print(f"Report -> {report_path}")
    print(f"URL    -> http://localhost:8181/{report_path.name}")

if __name__ == "__main__":
    main()
