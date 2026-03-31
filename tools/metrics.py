#!/usr/bin/env python3
"""
metrics.py — Compare taxonomy against a reference (gold standard).

Usage:
    python tools/metrics.py [taxonomy.json] [reference.json]
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from taxonomy_core import load_taxonomy, compute_metrics

def main():
    tax_path = sys.argv[1] if len(sys.argv) > 1 else "taxonomy.json"
    ref_path = sys.argv[2] if len(sys.argv) > 2 else "reference/gold_standard.json"

    if not Path(tax_path).exists():
        print(f"ERROR: {tax_path} not found")
        sys.exit(1)
    if not Path(ref_path).exists():
        print(f"ERROR: {ref_path} not found")
        sys.exit(1)

    taxonomy = load_taxonomy(tax_path)
    reference = load_taxonomy(ref_path)
    metrics = compute_metrics(taxonomy, reference)

    print("=" * 60)
    print("TAXONOMY QUALITY METRICS")
    print("=" * 60)
    print(f"Predicted nodes: {metrics['pred_nodes']}")
    print(f"Gold nodes:      {metrics['gold_nodes']}")
    print(f"Common nodes:    {metrics['common_nodes']}")
    print()
    print(f"Edge Precision:  {metrics['edge_precision']:.4f}")
    print(f"Edge Recall:     {metrics['edge_recall']:.4f}")
    print(f"Edge F1:         {metrics['edge_f1']:.4f}")
    print()
    print(f"Node Coverage:   {metrics['node_coverage']:.4f}")
    print(f"Ancestor F1:     {metrics['ancestor_f1']:.4f}")

if __name__ == "__main__":
    main()
