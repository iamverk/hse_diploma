"""
taxonomy_core.py — Core operations for Taxonomy-as-Code.

Shared logic used by both MCP server and CLI tools.
Taxonomy is stored as a nested JSON structure and manipulated via networkx DiGraph.
"""

from __future__ import annotations

import json
import copy
from pathlib import Path
from typing import Optional
from collections import Counter

try:
    import networkx as nx
except ImportError:
    raise ImportError("networkx is required: pip install networkx")


def load_taxonomy(path: str | Path) -> dict:
    """Load taxonomy from a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_taxonomy(taxonomy: dict, path: str | Path) -> None:
    """Save taxonomy to a JSON file (pretty-printed)."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(taxonomy, f, ensure_ascii=False, indent=2)


def _taxonomy_to_graph(taxonomy: dict) -> nx.DiGraph:
    """Convert nested taxonomy dict to a networkx DiGraph."""
    G = nx.DiGraph()

    def _walk(node: dict, parent_id: Optional[str] = None):
        nid = node["id"]
        G.add_node(nid, name=node.get("name", nid), description=node.get("description", ""))
        if parent_id is not None:
            G.add_edge(parent_id, nid)
        for child in node.get("children", []):
            _walk(child, nid)

    _walk(taxonomy)
    return G


def _graph_to_taxonomy(G: nx.DiGraph, root_id: str) -> dict:
    """Convert networkx DiGraph back to nested taxonomy dict."""
    data = G.nodes[root_id]
    node = {
        "id": root_id,
        "name": data.get("name", root_id),
        "description": data.get("description", ""),
    }
    children_ids = sorted(G.successors(root_id))
    if children_ids:
        node["children"] = [_graph_to_taxonomy(G, cid) for cid in children_ids]
    return node


def _find_root(G: nx.DiGraph) -> str:
    """Find the root node (node with in-degree 0)."""
    roots = [n for n, d in G.in_degree() if d == 0]
    if len(roots) != 1:
        raise ValueError(f"Expected exactly 1 root, found {len(roots)}: {roots}")
    return roots[0]


def add_node(taxonomy: dict, parent_id: str, node_id: str, name: str,
             description: str = "") -> dict:
    """Add a new node under the specified parent. Returns updated taxonomy."""
    taxonomy = copy.deepcopy(taxonomy)

    def _find_and_add(node: dict) -> bool:
        if node["id"] == parent_id:
            if "children" not in node:
                node["children"] = []
            if any(c["id"] == node_id for c in node["children"]):
                raise ValueError(f"Node '{node_id}' already exists under '{parent_id}'")
            node["children"].append({
                "id": node_id,
                "name": name,
                "description": description,
            })
            return True
        for child in node.get("children", []):
            if _find_and_add(child):
                return True
        return False

    if not _find_and_add(taxonomy):
        raise ValueError(f"Parent node '{parent_id}' not found")
    return taxonomy


def delete_node(taxonomy: dict, node_id: str) -> dict:
    """Delete a node and all its descendants. Returns updated taxonomy."""
    taxonomy = copy.deepcopy(taxonomy)
    if taxonomy["id"] == node_id:
        raise ValueError("Cannot delete root node")

    def _remove(node: dict) -> bool:
        if "children" not in node:
            return False
        for i, child in enumerate(node["children"]):
            if child["id"] == node_id:
                node["children"].pop(i)
                if not node["children"]:
                    del node["children"]
                return True
            if _remove(child):
                return True
        return False

    if not _remove(taxonomy):
        raise ValueError(f"Node '{node_id}' not found")
    return taxonomy


def move_node(taxonomy: dict, node_id: str, new_parent_id: str) -> dict:
    """Move a node (with its subtree) to a new parent. Returns updated taxonomy."""
    G = _taxonomy_to_graph(taxonomy)
    if node_id not in G:
        raise ValueError(f"Node '{node_id}' not found")
    if new_parent_id not in G:
        raise ValueError(f"New parent '{new_parent_id}' not found")
    if node_id == _find_root(G):
        raise ValueError("Cannot move root node")
    if new_parent_id in nx.descendants(G, node_id):
        raise ValueError(f"Cannot move '{node_id}' under its own descendant '{new_parent_id}'")

    old_parent = list(G.predecessors(node_id))[0]
    G.remove_edge(old_parent, node_id)
    G.add_edge(new_parent_id, node_id)

    root = _find_root(G)
    return _graph_to_taxonomy(G, root)


def search_nodes(taxonomy: dict, query: str) -> list[dict]:
    """Search nodes by name (case-insensitive substring match)."""
    results = []
    query_lower = query.lower()

    def _search(node: dict, path: list[str]):
        if query_lower in node.get("name", "").lower() or query_lower in node.get("id", "").lower():
            results.append({
                "id": node["id"],
                "name": node.get("name", ""),
                "path": " > ".join(path + [node.get("name", node["id"])]),
            })
        for child in node.get("children", []):
            _search(child, path + [node.get("name", node["id"])])

    _search(taxonomy, [])
    return results


def get_subtree(taxonomy: dict, node_id: str, max_depth: int = 3) -> Optional[dict]:
    """Get a subtree rooted at node_id, limited to max_depth levels."""
    def _find(node: dict) -> Optional[dict]:
        if node["id"] == node_id:
            return node
        for child in node.get("children", []):
            result = _find(child)
            if result:
                return result
        return None

    subtree = _find(taxonomy)
    if subtree is None:
        return None

    def _trim(node: dict, depth: int) -> dict:
        trimmed = {"id": node["id"], "name": node.get("name", ""), "description": node.get("description", "")}
        if depth < max_depth and "children" in node:
            trimmed["children"] = [_trim(c, depth + 1) for c in node["children"]]
        elif "children" in node:
            trimmed["children_count"] = len(node["children"])
        return trimmed

    return _trim(copy.deepcopy(subtree), 0)


def validate(taxonomy: dict) -> dict:
    """Validate taxonomy structure. Returns {valid: bool, errors: [...], warnings: [...]}."""
    errors = []
    warnings = []

    try:
        G = _taxonomy_to_graph(taxonomy)
    except Exception as e:
        return {"valid": False, "errors": [f"Cannot parse taxonomy: {e}"], "warnings": []}

    if not nx.is_directed_acyclic_graph(G):
        cycles = list(nx.simple_cycles(G))
        errors.append(f"Graph contains cycles: {cycles[:3]}")

    roots = [n for n, d in G.in_degree() if d == 0]
    if len(roots) != 1:
        errors.append(f"Expected 1 root, found {len(roots)}: {roots}")

    isolates = list(nx.isolates(G))
    if len(G.nodes) > 1 and isolates:
        errors.append(f"Orphan nodes (no connections): {isolates}")

    all_ids = []
    def _collect_ids(node):
        all_ids.append(node["id"])
        for c in node.get("children", []):
            _collect_ids(c)
    _collect_ids(taxonomy)
    dupes = [k for k, v in Counter(all_ids).items() if v > 1]
    if dupes:
        errors.append(f"Duplicate node IDs: {dupes}")

    if roots and not errors:
        root = roots[0]
        longest_path = nx.dag_longest_path_length(G)
        if longest_path > 7:
            warnings.append(f"Max depth is {longest_path}, recommended ≤ 7")

    for node in G.nodes():
        successors = list(G.successors(node))
        if len(successors) == 1:
            warnings.append(f"Node '{node}' has only 1 child — consider merging")

    for node in G.nodes():
        successors = list(G.successors(node))
        if len(successors) > 20:
            warnings.append(f"Node '{node}' has {len(successors)} children — consider splitting")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "total_nodes": G.number_of_nodes(),
            "total_edges": G.number_of_edges(),
            "max_depth": nx.dag_longest_path_length(G) if nx.is_directed_acyclic_graph(G) else -1,
            "leaf_nodes": sum(1 for n in G.nodes() if G.out_degree(n) == 0),
        }
    }


def compute_metrics(taxonomy: dict, reference: dict) -> dict:
    """Compute quality metrics comparing taxonomy to a reference (gold standard)."""
    G_pred = _taxonomy_to_graph(taxonomy)
    G_gold = _taxonomy_to_graph(reference)

    pred_edges = set(G_pred.edges())
    gold_edges = set(G_gold.edges())

    if len(pred_edges) == 0:
        precision = 0.0
    else:
        precision = len(pred_edges & gold_edges) / len(pred_edges)

    if len(gold_edges) == 0:
        recall = 0.0
    else:
        recall = len(pred_edges & gold_edges) / len(gold_edges)

    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    pred_nodes = set(G_pred.nodes())
    gold_nodes = set(G_gold.nodes())
    node_coverage = len(pred_nodes & gold_nodes) / len(gold_nodes) if gold_nodes else 0.0

    ancestor_precisions = []
    ancestor_recalls = []
    common_nodes = pred_nodes & gold_nodes
    for node in common_nodes:
        pred_ancestors = set(nx.ancestors(G_pred, node))
        gold_ancestors = set(nx.ancestors(G_gold, node))
        if pred_ancestors:
            ancestor_precisions.append(len(pred_ancestors & gold_ancestors) / len(pred_ancestors))
        if gold_ancestors:
            ancestor_recalls.append(len(pred_ancestors & gold_ancestors) / len(gold_ancestors))

    avg_anc_p = sum(ancestor_precisions) / len(ancestor_precisions) if ancestor_precisions else 0.0
    avg_anc_r = sum(ancestor_recalls) / len(ancestor_recalls) if ancestor_recalls else 0.0
    anc_f1 = 2 * avg_anc_p * avg_anc_r / (avg_anc_p + avg_anc_r) if (avg_anc_p + avg_anc_r) > 0 else 0.0

    depths = {}
    if nx.is_directed_acyclic_graph(G_pred):
        root = _find_root(G_pred)
        for node in G_pred.nodes():
            try:
                d = nx.shortest_path_length(G_pred, root, node)
                depths.setdefault(d, []).append(G_pred.out_degree(node))
            except nx.NetworkXNoPath:
                pass

    return {
        "edge_precision": round(precision, 4),
        "edge_recall": round(recall, 4),
        "edge_f1": round(f1, 4),
        "node_coverage": round(node_coverage, 4),
        "ancestor_f1": round(anc_f1, 4),
        "pred_nodes": len(pred_nodes),
        "gold_nodes": len(gold_nodes),
        "common_nodes": len(common_nodes),
    }


def lint(taxonomy: dict) -> list[dict]:
    """Find structural anomalies in the taxonomy."""
    issues = []
    G = _taxonomy_to_graph(taxonomy)

    for node in nx.isolates(G):
        issues.append({"type": "orphan", "node": node, "severity": "error",
                        "message": f"Node '{node}' has no connections"})

    for node in G.nodes():
        children = list(G.successors(node))
        if len(children) == 1:
            issues.append({"type": "single_child", "node": node, "severity": "warning",
                            "message": f"Node '{node}' has only 1 child '{children[0]}' — consider merging"})

    for node in G.nodes():
        children = list(G.successors(node))
        if len(children) > 15:
            issues.append({"type": "high_fanout", "node": node, "severity": "warning",
                            "message": f"Node '{node}' has {len(children)} children — consider splitting"})

    for node in G.nodes():
        name = G.nodes[node].get("name", "")
        if not name or name.strip() == "":
            issues.append({"type": "empty_name", "node": node, "severity": "error",
                            "message": f"Node '{node}' has an empty name"})

    def _check_sibling_dupes(node_dict: dict):
        children = node_dict.get("children", [])
        names = [c.get("name", "") for c in children]
        seen = set()
        for n in names:
            if n in seen:
                issues.append({"type": "duplicate_sibling", "node": node_dict["id"],
                                "severity": "warning",
                                "message": f"Duplicate sibling name '{n}' under '{node_dict['id']}'"})
            seen.add(n)
        for c in children:
            _check_sibling_dupes(c)

    _check_sibling_dupes(taxonomy)

    if nx.is_directed_acyclic_graph(G):
        longest = nx.dag_longest_path_length(G)
        if longest > 7:
            path = nx.dag_longest_path(G)
            issues.append({"type": "excessive_depth", "node": path[-1], "severity": "warning",
                            "message": f"Max depth is {longest} (path: {' > '.join(path[:4])}...)"})

    return issues


def diff(taxonomy_old: dict, taxonomy_new: dict) -> dict:
    """Compare two taxonomy versions and return differences."""
    G_old = _taxonomy_to_graph(taxonomy_old)
    G_new = _taxonomy_to_graph(taxonomy_new)

    old_nodes = set(G_old.nodes())
    new_nodes = set(G_new.nodes())
    old_edges = set(G_old.edges())
    new_edges = set(G_new.edges())

    added_nodes = new_nodes - old_nodes
    removed_nodes = old_nodes - new_nodes
    added_edges = new_edges - old_edges
    removed_edges = old_edges - new_edges

    moved = []
    for node in old_nodes & new_nodes:
        old_parents = set(G_old.predecessors(node))
        new_parents = set(G_new.predecessors(node))
        if old_parents != new_parents and old_parents and new_parents:
            moved.append({
                "node": node,
                "from_parent": list(old_parents)[0],
                "to_parent": list(new_parents)[0],
            })

    return {
        "added_nodes": sorted(added_nodes),
        "removed_nodes": sorted(removed_nodes),
        "added_edges": [{"from": e[0], "to": e[1]} for e in sorted(added_edges)],
        "removed_edges": [{"from": e[0], "to": e[1]} for e in sorted(removed_edges)],
        "moved_nodes": moved,
        "summary": {
            "nodes_added": len(added_nodes),
            "nodes_removed": len(removed_nodes),
            "edges_added": len(added_edges),
            "edges_removed": len(removed_edges),
            "nodes_moved": len(moved),
        }
    }


def print_tree(taxonomy: dict, indent: int = 0) -> str:
    """Return a human-readable tree string."""
    lines = []
    prefix = "  " * indent + ("├── " if indent > 0 else "")
    lines.append(f"{prefix}{taxonomy.get('name', taxonomy['id'])}")
    for child in taxonomy.get("children", []):
        lines.append(print_tree(child, indent + 1))
    return "\n".join(lines)
