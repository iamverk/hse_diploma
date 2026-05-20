#!/usr/bin/env python3
"""
lint.py — Find structural anomalies in the taxonomy.

Usage:
    python tools/lint.py [taxonomy.json]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from taxonomy_core import load_taxonomy, lint

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "taxonomy.json"
    tax = load_taxonomy(path)
    issues = lint(tax)

    if not issues:
        print("No structural anomalies found.")
        return

    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]

    if errors:
        print("ERRORS:")
        for i in errors:
            print(f"  [{i['type']}] {i['message']}")

    if warnings:
        print("WARNINGS:")
        for i in warnings:
            print(f"  [{i['type']}] {i['message']}")

    print(f"\nTotal: {len(errors)} errors, {len(warnings)} warnings")
    sys.exit(1 if errors else 0)

if __name__ == "__main__":
    main()
