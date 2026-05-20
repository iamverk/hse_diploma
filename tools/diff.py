#!/usr/bin/env python3
"""
diff.py — Compare two taxonomy versions and show differences.

Usage:
    python tools/diff.py taxonomy_v1.json taxonomy_v2.json
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from taxonomy_core import load_taxonomy, diff

def main():
    if len(sys.argv) < 3:
        print("Usage: python tools/diff.py <old.json> <new.json>")
        sys.exit(1)

    old = load_taxonomy(sys.argv[1])
    new = load_taxonomy(sys.argv[2])
    d = diff(old, new)
    s = d["summary"]

    print("=" * 50)
    print("TAXONOMY DIFF")
    print("=" * 50)
    print(f"Nodes added:   +{s['nodes_added']}")
    print(f"Nodes removed: -{s['nodes_removed']}")
    print(f"Nodes moved:    {s['nodes_moved']}")
    print(f"Edges added:   +{s['edges_added']}")
    print(f"Edges removed: -{s['edges_removed']}")

    if d["added_nodes"]:
        print(f"\nNew nodes: {', '.join(d['added_nodes'])}")
    if d["removed_nodes"]:
        print(f"Removed:   {', '.join(d['removed_nodes'])}")
    if d["moved_nodes"]:
        print("Moved:")
        for m in d["moved_nodes"]:
            print(f"  {m['node']}: {m['from_parent']} -> {m['to_parent']}")

if __name__ == "__main__":
    main()
