#!/usr/bin/env python3
"""
akeneo_export.py — Export taxonomy.json to Akeneo PIM CSV format.

Akeneo expects categories as a flat CSV with parent references:
    code;parent;label-en_US;label-ru_RU
    products;;Products;Товары
    electronics;products;Electronics;Электроника
    laptops;computers;Laptops;Ноутбуки

Akeneo conventions:
    • code: lowercase_snake_case (we already use this)
    • parent: empty for root, parent code for others
    • label-{locale}: human-readable name per locale (we only emit en_US)
    • One row per category (depth-first traversal)

Optional XLSX export via openpyxl if installed.

Usage:
    python tools/akeneo_export.py taxonomy.json
    python tools/akeneo_export.py taxonomy.json --xlsx
    python tools/akeneo_export.py taxonomy.json --output mytax.csv
    python tools/akeneo_export.py taxonomy.json --json   # Akeneo REST API payload
"""

import csv
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from taxonomy_core import load_taxonomy


def flatten(taxonomy, parent_code=""):
    """Depth-first walk: yield (code, parent_code, label) tuples."""
    code = taxonomy["id"]
    label = taxonomy.get("name", code)
    yield (code, parent_code, label, taxonomy.get("description", ""))
    for child in taxonomy.get("children", []):
        yield from flatten(child, parent_code=code)


def export_csv(taxonomy, out_path):
    rows = list(flatten(taxonomy))
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        w.writerow(["code", "parent", "label-en_US"])
        for code, parent, label, _ in rows:
            w.writerow([code, parent, label])
    return len(rows)


def export_xlsx(taxonomy, out_path):
    try:
        from openpyxl import Workbook
    except ImportError:
        return None
    rows = list(flatten(taxonomy))
    wb = Workbook()
    ws = wb.active
    ws.title = "Categories"
    ws.append(["code", "parent", "label-en_US", "description"])
    for code, parent, label, desc in rows:
        ws.append([code, parent, label, desc])
    # Column widths
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 30
    ws.column_dimensions["C"].width = 35
    ws.column_dimensions["D"].width = 60
    wb.save(out_path)
    return len(rows)


def export_rest_api_payload(taxonomy):
    """Return a list of dicts in Akeneo REST API format for POST /api/rest/v1/categories."""
    rows = list(flatten(taxonomy))
    payload = []
    for code, parent, label, _ in rows:
        item = {
            "code": code,
            "parent": parent if parent else None,
            "labels": {"en_US": label},
        }
        payload.append(item)
    return payload


def main():
    args = sys.argv[1:]
    paths = [a for a in args if not a.startswith("--")]
    tax_path = paths[0] if paths else "taxonomy.json"

    out = None
    if "--output" in args:
        out = args[args.index("--output") + 1]

    use_xlsx = "--xlsx" in args
    use_json = "--json" in args

    if not os.path.exists(tax_path):
        print(f"ERROR: {tax_path} not found", file=sys.stderr)
        sys.exit(1)

    tax = load_taxonomy(tax_path)
    base = Path(tax_path).stem

    if use_json:
        payload = export_rest_api_payload(tax)
        out = out or f"{base}_akeneo.json"
        with open(out, "w") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"✓ Akeneo REST API payload: {out}  ({len(payload)} categories)")
        print(f"  Use: curl -X POST $AKENEO/api/rest/v1/categories -d @{out}")
        return

    if use_xlsx:
        out = out or f"{base}_akeneo.xlsx"
        n = export_xlsx(tax, out)
        if n is None:
            print("ERROR: openpyxl not installed. pip install openpyxl", file=sys.stderr)
            sys.exit(1)
        print(f"✓ Akeneo XLSX: {out}  ({n} categories)")
    else:
        out = out or f"{base}_akeneo.csv"
        n = export_csv(tax, out)
        print(f"✓ Akeneo CSV: {out}  ({n} categories)")
        print(f"  Import: System → Import profiles → CSV/XLSX category import")


if __name__ == "__main__":
    main()
