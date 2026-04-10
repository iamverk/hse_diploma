#!/usr/bin/env python3
"""
metrics_v2.py — Reference-free taxonomy quality metrics.

Metrics:
  1. NLIV  — Natural Language Inference Validity (cosine similarity proxy)
  2. CSC   — Concept Semantic Coherence (Spearman: cosine vs Wu-Palmer)
  3. NTED  — Normalized Tree Edit Distance proxy (edge Jaccard)
  4. Structural Health — chains, balance, depth, branching
  5. Composite Score — weighted combination for stopping criterion

Usage:
    python tools/metrics_v2.py [taxonomy.json] [previous_taxonomy.json]
    python tools/metrics_v2.py --json   # machine-readable output

Dependencies:
    pip install sentence-transformers networkx scipy numpy
"""

import json
import sys
import os
import numpy as np
import networkx as nx
from scipy.stats import spearmanr
from collections import defaultdict

# Add tools dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from taxonomy_core import load_taxonomy, _taxonomy_to_graph


# ============================================================
# Embedder singleton (lazy load)
# ============================================================

_EMBEDDER = None

def _get_embedder():
    global _EMBEDDER
    if _EMBEDDER is None:
        from sentence_transformers import SentenceTransformer
        _EMBEDDER = SentenceTransformer('all-MiniLM-L6-v2')
    return _EMBEDDER


def _node_name(G, node_id):
    """Get human-readable name for a node."""
    data = G.nodes.get(node_id, {})
    return data.get("name", node_id)


# ============================================================
# 1. NLIV (Natural Language Inference Validity)
# ============================================================

def compute_nliv(G, embedder=None):
    """
    For each edge (parent, child), compute cosine similarity of embeddings
    as a proxy for IS-A validity.

    Returns:
        dict with nliv_mean, nliv_min, weak_edges, edge_scores
    """
    if embedder is None:
        embedder = _get_embedder()

    edges = list(G.edges())
    if not edges:
        return {"nliv_mean": 0.0, "nliv_min": 0.0, "weak_edges": [], "edge_scores": {}}

    # Collect unique names
    all_names = list(set(_node_name(G, n) for n in G.nodes()))
    name_to_idx = {name: i for i, name in enumerate(all_names)}
    embeddings = embedder.encode(all_names, normalize_embeddings=True)

    edge_scores = {}
    for parent, child in edges:
        p_name = _node_name(G, parent)
        c_name = _node_name(G, child)
        p_emb = embeddings[name_to_idx[p_name]]
        c_emb = embeddings[name_to_idx[c_name]]
        score = float(np.dot(p_emb, c_emb))
        edge_scores[(parent, child)] = score

    scores = list(edge_scores.values())
    weak = [(p, c, s) for (p, c), s in edge_scores.items() if s < 0.3]
    # Sort weak edges by score ascending (worst first)
    weak.sort(key=lambda x: x[2])

    return {
        "nliv_mean": float(np.mean(scores)),
        "nliv_min": float(np.min(scores)),
        "weak_edges": weak,
        "edge_scores": edge_scores
    }


# ============================================================
# 2. CSC (Concept Semantic Coherence)
# ============================================================

def _wu_palmer_similarity(G, u, v, root):
    """Wu-Palmer similarity for two nodes in a tree."""
    try:
        undirected = G.to_undirected()
        path_u = nx.shortest_path(undirected, root, u)
        path_v = nx.shortest_path(undirected, root, v)

        # LCA = last common node in paths from root
        lca_depth = 0
        for a, b in zip(path_u, path_v):
            if a == b:
                lca_depth += 1
            else:
                break

        depth_u = len(path_u) - 1
        depth_v = len(path_v) - 1

        if depth_u + depth_v == 0:
            return 1.0

        return (2 * (lca_depth - 1)) / (depth_u + depth_v)
    except Exception:
        return 0.0


def compute_csc(G, embedder=None, sample_size=200):
    """
    Spearman correlation between:
      - pairwise cosine similarity of node name embeddings
      - pairwise Wu-Palmer structural similarity

    Returns:
        dict with csc_score, p_value, n_pairs
    """
    if embedder is None:
        embedder = _get_embedder()

    nodes = list(G.nodes())
    if len(nodes) < 3:
        return {"csc_score": 0.0, "p_value": 1.0, "n_pairs": 0}

    # Find root
    roots = [n for n in nodes if G.in_degree(n) == 0]
    root = roots[0] if roots else nodes[0]

    all_names = [_node_name(G, n) for n in nodes]
    embeddings = embedder.encode(all_names, normalize_embeddings=True)

    import itertools
    import random
    all_pairs = list(itertools.combinations(range(len(nodes)), 2))
    if len(all_pairs) > sample_size:
        random.seed(42)
        all_pairs = random.sample(all_pairs, sample_size)

    semantic_sims = []
    structural_sims = []

    for i, j in all_pairs:
        sem = float(np.dot(embeddings[i], embeddings[j]))
        struct = _wu_palmer_similarity(G, nodes[i], nodes[j], root)
        semantic_sims.append(sem)
        structural_sims.append(struct)

    if len(semantic_sims) < 3:
        return {"csc_score": 0.0, "p_value": 1.0, "n_pairs": 0}

    corr, p_val = spearmanr(semantic_sims, structural_sims)

    return {
        "csc_score": float(corr) if not np.isnan(corr) else 0.0,
        "p_value": float(p_val),
        "n_pairs": len(all_pairs)
    }


# ============================================================
# 3. NTED proxy (edge Jaccard distance)
# ============================================================

def compute_nted_proxy(G_current, G_previous):
    """
    Edge Jaccard distance between current and previous taxonomy.
    Returns dict with nted, edges_added, edges_removed, edges_unchanged.
    """
    if G_previous is None:
        return {
            "nted": 1.0,
            "edges_added": len(G_current.edges()),
            "edges_removed": 0,
            "edges_unchanged": 0
        }

    # Use node names for edge comparison (IDs may differ between iterations)
    def _name_edges(G):
        return set(
            (_node_name(G, u), _node_name(G, v))
            for u, v in G.edges()
        )

    edges_curr = _name_edges(G_current)
    edges_prev = _name_edges(G_previous)

    added = edges_curr - edges_prev
    removed = edges_prev - edges_curr
    unchanged = edges_curr & edges_prev
    union = edges_curr | edges_prev

    jaccard_dist = 1.0 - (len(unchanged) / len(union)) if union else 0.0

    return {
        "nted": float(jaccard_dist),
        "edges_added": len(added),
        "edges_removed": len(removed),
        "edges_unchanged": len(unchanged)
    }


# ============================================================
# 4. Structural Health
# ============================================================

def compute_structural_health(G):
    """
    Structural metrics: chains, balance, depth, branching.
    """
    nodes = list(G.nodes())
    if not nodes:
        return {}

    roots = [n for n in nodes if G.in_degree(n) == 0]
    leaves = [n for n in nodes if G.out_degree(n) == 0]
    internal = [n for n in nodes if G.out_degree(n) > 0]
    chains = [n for n in internal if G.out_degree(n) == 1]

    branching = [G.out_degree(n) for n in internal] if internal else [0]

    root = roots[0] if roots else nodes[0]
    depths = {}
    for n in nodes:
        try:
            depths[n] = nx.shortest_path_length(G, root, n)
        except Exception:
            depths[n] = 0

    depth_values = list(depths.values())

    return {
        "node_count": len(nodes),
        "edge_count": len(G.edges()),
        "leaf_count": len(leaves),
        "internal_count": len(internal),
        "chain_count": len(chains),
        "chain_nodes": [_node_name(G, n) for n in chains],
        "max_depth": max(depth_values) if depth_values else 0,
        "mean_depth": float(np.mean(depth_values)) if depth_values else 0,
        "branching_mean": float(np.mean(branching)),
        "branching_std": float(np.std(branching)),
        "branching_cv": float(np.std(branching) / np.mean(branching)) if np.mean(branching) > 0 else 0,
        "leaf_ratio": len(leaves) / len(nodes) if nodes else 0,
    }


# ============================================================
# 5. Composite Score
# ============================================================

def compute_composite_score(nliv_mean, csc_score, structural_health):
    """
    Weighted composite: NLIV 0.4 + CSC 0.3 + structural 0.3.
    Structural sub-score penalizes chains and imbalance.
    """
    chain_penalty = min(structural_health.get("chain_count", 0) * 0.05, 0.3)
    cv_penalty = min(structural_health.get("branching_cv", 0) * 0.2, 0.3)
    struct_score = max(0, 1.0 - chain_penalty - cv_penalty)

    composite = 0.4 * max(nliv_mean, 0) + 0.3 * max(csc_score, 0) + 0.3 * struct_score
    return float(composite)


# ============================================================
# 6. compute_all_metrics
# ============================================================

def compute_all_metrics(G_current, G_previous=None, embedder=None):
    """
    Compute all reference-free metrics.

    Args:
        G_current: networkx DiGraph of current taxonomy
        G_previous: networkx DiGraph of previous iteration (or None)
        embedder: SentenceTransformer (loaded automatically if None)

    Returns:
        dict with all metrics
    """
    if embedder is None:
        embedder = _get_embedder()

    nliv = compute_nliv(G_current, embedder)
    csc = compute_csc(G_current, embedder)
    nted = compute_nted_proxy(G_current, G_previous)
    structural = compute_structural_health(G_current)
    composite = compute_composite_score(nliv["nliv_mean"], csc["csc_score"], structural)

    return {
        "nliv": nliv,
        "csc": csc,
        "nted": nted,
        "structural": structural,
        "composite_score": composite
    }


# ============================================================
# CLI
# ============================================================

def main():
    taxonomy_path = sys.argv[1] if len(sys.argv) > 1 else "taxonomy.json"
    previous_path = sys.argv[2] if len(sys.argv) > 2 else None
    json_output = "--json" in sys.argv

    if not os.path.exists(taxonomy_path):
        print(f"ERROR: {taxonomy_path} not found", file=sys.stderr)
        sys.exit(1)

    tax = load_taxonomy(taxonomy_path)
    G = _taxonomy_to_graph(tax)

    G_prev = None
    if previous_path and os.path.exists(previous_path):
        prev_tax = load_taxonomy(previous_path)
        G_prev = _taxonomy_to_graph(prev_tax)

    metrics = compute_all_metrics(G, G_prev)

    if json_output:
        # Machine-readable: strip non-serializable fields
        output = {
            "nliv_mean": metrics["nliv"]["nliv_mean"],
            "nliv_min": metrics["nliv"]["nliv_min"],
            "weak_edges_count": len(metrics["nliv"]["weak_edges"]),
            "csc_score": metrics["csc"]["csc_score"],
            "csc_p_value": metrics["csc"]["p_value"],
            "nted": metrics["nted"]["nted"],
            "edges_added": metrics["nted"]["edges_added"],
            "edges_removed": metrics["nted"]["edges_removed"],
            "composite_score": metrics["composite_score"],
            **{k: v for k, v in metrics["structural"].items() if k != "chain_nodes"},
        }
        print(json.dumps(output, indent=2))
    else:
        # Human-readable
        print("=" * 60)
        print("REFERENCE-FREE TAXONOMY METRICS")
        print("=" * 60)
        print()
        s = metrics["structural"]
        print(f"Nodes: {s['node_count']}  Edges: {s['edge_count']}  "
              f"Leaves: {s['leaf_count']}  Max depth: {s['max_depth']}")
        print()
        print("--- NLIV (Edge Validity) ---")
        print(f"  Mean:  {metrics['nliv']['nliv_mean']:.4f}")
        print(f"  Min:   {metrics['nliv']['nliv_min']:.4f}")
        weak = metrics["nliv"]["weak_edges"]
        print(f"  Weak edges (NLIV < 0.3): {len(weak)}")
        for p, c, sc in weak[:5]:
            print(f"    {_node_name(G, p)} -> {_node_name(G, c)}: {sc:.3f}")
        print()
        print("--- CSC (Semantic Coherence) ---")
        print(f"  Score:   {metrics['csc']['csc_score']:.4f}")
        print(f"  p-value: {metrics['csc']['p_value']:.4f}")
        print(f"  Pairs:   {metrics['csc']['n_pairs']}")
        print()
        print("--- NTED (Stability) ---")
        n = metrics["nted"]
        print(f"  Distance:  {n['nted']:.4f}")
        print(f"  Added:     {n['edges_added']}  Removed: {n['edges_removed']}  "
              f"Unchanged: {n['edges_unchanged']}")
        print()
        print("--- Structural Health ---")
        print(f"  Chains:      {s['chain_count']}")
        if s["chain_nodes"]:
            print(f"    → {', '.join(s['chain_nodes'][:5])}")
        print(f"  Branching:   mean={s['branching_mean']:.1f}  "
              f"std={s['branching_std']:.1f}  CV={s['branching_cv']:.2f}")
        print(f"  Leaf ratio:  {s['leaf_ratio']:.2f}")
        print()
        print(f"{'=' * 60}")
        print(f"COMPOSITE SCORE: {metrics['composite_score']:.4f}")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
