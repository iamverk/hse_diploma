#!/usr/bin/env python3
"""
validate.py — Taxonomy structure validator.

Usage:
    python tools/validate.py [taxonomy.json]

Exit code 0 = valid, 1 = errors found.
Used as pre-commit hook and Ralph loop stop condition.
"""

import sys
import json
from pathlib import Path

# Add tools directory to path
sys.path.insert(0, str(Path(__file__).parent))
from taxonomy_core import load_taxonomy, validate, lint

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "taxonomy.json"

    if not Path(path).exists():
        print(f"ERROR: File not found: {path}")
        sys.exit(1)

    taxonomy = load_taxonomy(path)

    # Run validation
    result = validate(taxonomy)

    # Run linting
    issues = lint(taxonomy)
    lint_errors = [i for i in issues if i["severity"] == "error"]
    lint_warnings = [i for i in issues if i["severity"] == "warning"]

    # Print results
    print("=" * 60)
    print("TAXONOMY VALIDATION REPORT")
    print("=" * 60)
    print(f"File: {path}")
    print(f"Nodes: {result['stats']['total_nodes']}")
    print(f"Edges: {result['stats']['total_edges']}")
    print(f"Max depth: {result['stats']['max_depth']}")
    print(f"Leaf nodes: {result['stats']['leaf_nodes']}")
    print()

    if result["errors"]:
        print("ERRORS:")
        for e in result["errors"]:
            print(f"  [x] {e}")

    if lint_errors:
        print("LINT ERRORS:")
        for e in lint_errors:
            print(f"  [x] {e['message']}")

    if result["warnings"]:
        print("WARNINGS:")
        for w in result["warnings"]:
            print(f"  [!] {w}")

    if lint_warnings:
        print("LINT WARNINGS:")
        for w in lint_warnings:
            print(f"  [!] {w['message']}")

    all_errors = result["errors"] + lint_errors
    if all_errors:
        print(f"\nRESULT: FAILED ({len(all_errors)} errors)")
        sys.exit(1)
    else:
        total_warnings = len(result["warnings"]) + len(lint_warnings)
        print(f"\nRESULT: PASSED ({total_warnings} warnings)")
        sys.exit(0)


if __name__ == "__main__":
    main()
