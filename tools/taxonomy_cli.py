#!/usr/bin/env python3
"""
taxonomy_cli.py — CLI interface for taxonomy operations.

Used by Ralph loop agents through shell commands.

Usage:
    python tools/taxonomy_cli.py tree
    python tools/taxonomy_cli.py add-node --parent electronics --id smartphones --name "Smartphones"
    python tools/taxonomy_cli.py delete-node --id smartphones
    python tools/taxonomy_cli.py move-node --id smartphones --new-parent clothing
    python tools/taxonomy_cli.py search --query "phone"
    python tools/taxonomy_cli.py subtree --id electronics --depth 2
    python tools/taxonomy_cli.py validate
    python tools/taxonomy_cli.py metrics --reference reference/gold_standard.json
    python tools/taxonomy_cli.py lint
    python tools/taxonomy_cli.py diff --old taxonomy_v1.json --new taxonomy.json
    python tools/taxonomy_cli.py stats
"""

import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import taxonomy_core as tc


DEFAULT_TAXONOMY = "taxonomy.json"
DEFAULT_REFERENCE = "reference/gold_standard.json"


def cmd_tree(args):
    tax = tc.load_taxonomy(args.file)
    print(tc.print_tree(tax))


def cmd_add_node(args):
    tax = tc.load_taxonomy(args.file)
    tax = tc.add_node(tax, args.parent, args.id, args.name, args.description or "")
    tc.save_taxonomy(tax, args.file)
    print(f"Added '{args.name}' (id={args.id}) under '{args.parent}'")
    result = tc.validate(tax)
    print(f"Nodes: {result['stats']['total_nodes']} | Valid: {result['valid']}")


def cmd_delete_node(args):
    tax = tc.load_taxonomy(args.file)
    tax = tc.delete_node(tax, args.id)
    tc.save_taxonomy(tax, args.file)
    print(f"Deleted node '{args.id}' and its descendants")


def cmd_move_node(args):
    tax = tc.load_taxonomy(args.file)
    tax = tc.move_node(tax, args.id, args.new_parent)
    tc.save_taxonomy(tax, args.file)
    print(f"Moved '{args.id}' under '{args.new_parent}'")


def cmd_search(args):
    tax = tc.load_taxonomy(args.file)
    results = tc.search_nodes(tax, args.query)
    if not results:
        print(f"No nodes matching '{args.query}'")
    for r in results:
        print(f"  {r['id']}: {r['name']} ({r['path']})")


def cmd_subtree(args):
    tax = tc.load_taxonomy(args.file)
    sub = tc.get_subtree(tax, args.id, args.depth)
    if sub is None:
        print(f"Node '{args.id}' not found")
        sys.exit(1)
    print(json.dumps(sub, ensure_ascii=False, indent=2))


def cmd_validate(args):
    tax = tc.load_taxonomy(args.file)
    result = tc.validate(tax)
    issues = tc.lint(tax)

    print(f"Nodes: {result['stats']['total_nodes']} | Edges: {result['stats']['total_edges']} | "
          f"Depth: {result['stats']['max_depth']} | Leaves: {result['stats']['leaf_nodes']}")

    errors = result["errors"] + [i["message"] for i in issues if i["severity"] == "error"]
    warnings = result["warnings"] + [i["message"] for i in issues if i["severity"] == "warning"]

    for e in errors:
        print(f"  [ERROR] {e}")
    for w in warnings:
        print(f"  [WARN]  {w}")

    if errors:
        print(f"\nFAILED ({len(errors)} errors, {len(warnings)} warnings)")
        sys.exit(1)
    else:
        print(f"\nPASSED ({len(warnings)} warnings)")


def cmd_metrics(args):
    tax = tc.load_taxonomy(args.file)
    ref = tc.load_taxonomy(args.reference)
    m = tc.compute_metrics(tax, ref)
    print(f"Edge F1: {m['edge_f1']:.4f} (P={m['edge_precision']:.4f} R={m['edge_recall']:.4f})")
    print(f"Ancestor F1: {m['ancestor_f1']:.4f}")
    print(f"Node Coverage: {m['node_coverage']:.4f} ({m['common_nodes']}/{m['gold_nodes']})")


def cmd_lint(args):
    tax = tc.load_taxonomy(args.file)
    issues = tc.lint(tax)
    if not issues:
        print("No issues found.")
        return
    for i in issues:
        tag = "ERROR" if i["severity"] == "error" else "WARN"
        print(f"  [{tag}] {i['type']}: {i['message']}")
    print(f"\nTotal: {len(issues)} issues")


def cmd_diff(args):
    old = tc.load_taxonomy(args.old)
    new = tc.load_taxonomy(args.new)
    d = tc.diff(old, new)
    s = d["summary"]
    print(f"Added nodes:   {s['nodes_added']}")
    print(f"Removed nodes: {s['nodes_removed']}")
    print(f"Moved nodes:   {s['nodes_moved']}")
    print(f"Added edges:   {s['edges_added']}")
    print(f"Removed edges: {s['edges_removed']}")
    if d["added_nodes"]:
        print(f"\n  New: {', '.join(d['added_nodes'][:10])}")
    if d["removed_nodes"]:
        print(f"  Gone: {', '.join(d['removed_nodes'][:10])}")
    if d["moved_nodes"]:
        for m in d["moved_nodes"][:5]:
            print(f"  Moved: {m['node']} ({m['from_parent']} -> {m['to_parent']})")


def cmd_stats(args):
    tax = tc.load_taxonomy(args.file)
    result = tc.validate(tax)
    s = result["stats"]
    print(f"Total nodes:  {s['total_nodes']}")
    print(f"Total edges:  {s['total_edges']}")
    print(f"Max depth:    {s['max_depth']}")
    print(f"Leaf nodes:   {s['leaf_nodes']}")
    print(f"Inner nodes:  {s['total_nodes'] - s['leaf_nodes']}")
    if s['total_nodes'] > 1:
        print(f"Avg fanout:   {s['total_edges'] / max(s['total_nodes'] - s['leaf_nodes'], 1):.1f}")


def main():
    parser = argparse.ArgumentParser(description="Taxonomy-as-Code CLI")
    parser.add_argument("--file", "-f", default=DEFAULT_TAXONOMY, help="Path to taxonomy.json")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("tree", help="Print taxonomy as tree")
    sub.add_parser("stats", help="Show taxonomy statistics")
    sub.add_parser("validate", help="Validate taxonomy structure")
    sub.add_parser("lint", help="Find structural anomalies")

    p = sub.add_parser("add-node", help="Add a new node")
    p.add_argument("--parent", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--description", default="")

    p = sub.add_parser("delete-node", help="Delete a node")
    p.add_argument("--id", required=True)

    p = sub.add_parser("move-node", help="Move a node to a new parent")
    p.add_argument("--id", required=True)
    p.add_argument("--new-parent", required=True)

    p = sub.add_parser("search", help="Search nodes by name")
    p.add_argument("--query", "-q", required=True)

    p = sub.add_parser("subtree", help="Get subtree of a node")
    p.add_argument("--id", required=True)
    p.add_argument("--depth", type=int, default=3)

    p = sub.add_parser("metrics", help="Compare with reference taxonomy")
    p.add_argument("--reference", "-r", default=DEFAULT_REFERENCE)

    p = sub.add_parser("diff", help="Compare two taxonomy versions")
    p.add_argument("--old", required=True)
    p.add_argument("--new", required=True)

    args = parser.parse_args()
    cmd_map = {
        "tree": cmd_tree, "add-node": cmd_add_node, "delete-node": cmd_delete_node,
        "move-node": cmd_move_node, "search": cmd_search, "subtree": cmd_subtree,
        "validate": cmd_validate, "metrics": cmd_metrics, "lint": cmd_lint,
        "diff": cmd_diff, "stats": cmd_stats,
    }
    cmd_map[args.command](args)


if __name__ == "__main__":
    main()
