#!/usr/bin/env python3
"""
taxonomy_mcp_server.py — MCP server exposing taxonomy operations as tools.

Register in .cursor/mcp.json:
{
  "mcpServers": {
    "taxonomy": {
      "command": "python",
      "args": ["tools/taxonomy_mcp_server.py"]
    }
  }
}

Requires: pip install mcp networkx
"""

import json
import sys
import os
from pathlib import Path

# Add tools directory to path
sys.path.insert(0, str(Path(__file__).parent))
import taxonomy_core as tc

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("MCP SDK not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)

TAXONOMY_PATH = os.environ.get("TAXONOMY_PATH", "taxonomy.json")
REFERENCE_PATH = os.environ.get("REFERENCE_PATH", "reference/gold_standard.json")

mcp = FastMCP("taxonomy-server")


@mcp.tool()
def taxonomy_tree() -> str:
    """Show the current taxonomy as a tree."""
    tax = tc.load_taxonomy(TAXONOMY_PATH)
    return tc.print_tree(tax)


@mcp.tool()
def taxonomy_stats() -> str:
    """Get taxonomy statistics: node count, depth, leaves, etc."""
    tax = tc.load_taxonomy(TAXONOMY_PATH)
    result = tc.validate(tax)
    s = result["stats"]
    return json.dumps(s, indent=2)


@mcp.tool()
def taxonomy_add_node(parent_id: str, node_id: str, name: str, description: str = "") -> str:
    """Add a new node under the specified parent.

    Args:
        parent_id: ID of the parent node
        node_id: Unique ID for the new node (lowercase_snake_case)
        name: Display name of the new node
        description: Short description of the category
    """
    tax = tc.load_taxonomy(TAXONOMY_PATH)
    tax = tc.add_node(tax, parent_id, node_id, name, description)
    tc.save_taxonomy(tax, TAXONOMY_PATH)
    stats = tc.validate(tax)["stats"]
    return f"Added '{name}' (id={node_id}) under '{parent_id}'. Total nodes: {stats['total_nodes']}"


@mcp.tool()
def taxonomy_delete_node(node_id: str) -> str:
    """Delete a node and all its descendants.

    Args:
        node_id: ID of the node to delete
    """
    tax = tc.load_taxonomy(TAXONOMY_PATH)
    tax = tc.delete_node(tax, node_id)
    tc.save_taxonomy(tax, TAXONOMY_PATH)
    return f"Deleted '{node_id}' and its descendants."


@mcp.tool()
def taxonomy_move_node(node_id: str, new_parent_id: str) -> str:
    """Move a node (with its subtree) to a new parent.

    Args:
        node_id: ID of the node to move
        new_parent_id: ID of the new parent node
    """
    tax = tc.load_taxonomy(TAXONOMY_PATH)
    tax = tc.move_node(tax, node_id, new_parent_id)
    tc.save_taxonomy(tax, TAXONOMY_PATH)
    return f"Moved '{node_id}' under '{new_parent_id}'."


@mcp.tool()
def taxonomy_search(query: str) -> str:
    """Search nodes by name (case-insensitive).

    Args:
        query: Search string to match against node names
    """
    tax = tc.load_taxonomy(TAXONOMY_PATH)
    results = tc.search_nodes(tax, query)
    if not results:
        return f"No nodes matching '{query}'"
    lines = [f"  {r['id']}: {r['name']} ({r['path']})" for r in results]
    return f"Found {len(results)} matches:\n" + "\n".join(lines)


@mcp.tool()
def taxonomy_get_subtree(node_id: str, max_depth: int = 3) -> str:
    """Get a subtree rooted at the specified node.

    Args:
        node_id: ID of the root node of the subtree
        max_depth: Maximum depth to traverse (default 3)
    """
    tax = tc.load_taxonomy(TAXONOMY_PATH)
    sub = tc.get_subtree(tax, node_id, max_depth)
    if sub is None:
        return f"Node '{node_id}' not found"
    return json.dumps(sub, ensure_ascii=False, indent=2)


@mcp.tool()
def taxonomy_validate() -> str:
    """Validate taxonomy structure: check DAG, cycles, orphans, duplicates."""
    tax = tc.load_taxonomy(TAXONOMY_PATH)
    result = tc.validate(tax)
    issues = tc.lint(tax)

    lines = []
    lines.append(f"Valid: {result['valid']}")
    lines.append(f"Nodes: {result['stats']['total_nodes']} | Depth: {result['stats']['max_depth']}")

    for e in result["errors"]:
        lines.append(f"  [ERROR] {e}")
    for i in issues:
        tag = "ERROR" if i["severity"] == "error" else "WARN"
        lines.append(f"  [{tag}] {i['message']}")
    for w in result["warnings"]:
        lines.append(f"  [WARN] {w}")

    return "\n".join(lines)


@mcp.tool()
def taxonomy_metrics() -> str:
    """Compute quality metrics comparing current taxonomy to the gold standard reference."""
    if not Path(REFERENCE_PATH).exists():
        return f"Reference file not found: {REFERENCE_PATH}"
    tax = tc.load_taxonomy(TAXONOMY_PATH)
    ref = tc.load_taxonomy(REFERENCE_PATH)
    m = tc.compute_metrics(tax, ref)
    return (f"Edge F1: {m['edge_f1']:.4f} (P={m['edge_precision']:.4f} R={m['edge_recall']:.4f})\n"
            f"Ancestor F1: {m['ancestor_f1']:.4f}\n"
            f"Node Coverage: {m['node_coverage']:.4f} ({m['common_nodes']}/{m['gold_nodes']})")


@mcp.tool()
def taxonomy_lint() -> str:
    """Find structural anomalies: orphans, single-child nodes, high fanout, etc."""
    tax = tc.load_taxonomy(TAXONOMY_PATH)
    issues = tc.lint(tax)
    if not issues:
        return "No issues found."
    lines = []
    for i in issues:
        tag = "ERROR" if i["severity"] == "error" else "WARN"
        lines.append(f"  [{tag}] {i['type']}: {i['message']}")
    return f"{len(issues)} issues found:\n" + "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")
