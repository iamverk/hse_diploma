#!/usr/bin/env python3
"""
metrics_v2.py — Reference-free taxonomy quality metrics.

Metrics:
  1. CES   — Cosine Edge Score (embedding cosine for parent-child edges)
  2. CSC   — Concept Semantic Coherence (Spearman: cosine vs Wu-Palmer)
  3. NTED  — Normalized Tree Edit Distance proxy (edge Jaccard)
  4. Structural Health — chains, balance, depth, branching
  5. RFTQ-D — deterministic weighted quality score for stopping criterion

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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from taxonomy_core import load_taxonomy, _taxonomy_to_graph


_EMBEDDER = None

def _get_embedder():
    global _EMBEDDER
    if _EMBEDDER is None:
        from sentence_transformers import SentenceTransformer
        _EMBEDDER = SentenceTransformer('all-MiniLM-L6-v2', local_files_only=True)
    return _EMBEDDER


def _node_name(G, node_id):
    """Get human-readable name for a node."""
    data = G.nodes.get(node_id, {})
    return data.get("name", node_id)


def compute_ces(G, embedder=None):
    """
    For each edge (parent, child), compute cosine similarity of embeddings
    as a proxy for IS-A validity.

    Returns:
        dict with primary ces_mean/ces_min keys and legacy nliv_mean/nliv_min
        aliases for older CSV/report consumers.
    """
    if embedder is None:
        embedder = _get_embedder()

    edges = list(G.edges())
    if not edges:
        return {"ces_mean": 0.0, "ces_min": 0.0, "nliv_mean": 0.0, "nliv_min": 0.0, "weak_edges": [], "edge_scores": {}}

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
    weak.sort(key=lambda x: x[2])

    ces_mean = float(np.mean(scores))
    ces_min = float(np.min(scores))
    return {
        "ces_mean": ces_mean,
        "ces_min": ces_min,
        "nliv_mean": ces_mean,
        "nliv_min": ces_min,
        "weak_edges": weak,
        "edge_scores": edge_scores
    }


def compute_nliv(G, embedder=None):
    """Legacy alias for compute_ces; kept for older scripts and notebooks."""
    return compute_ces(G, embedder)


def _wu_palmer_similarity(G, u, v, root):
    """Wu-Palmer similarity for two nodes in a tree."""
    try:
        undirected = G.to_undirected()
        path_u = nx.shortest_path(undirected, root, u)
        path_v = nx.shortest_path(undirected, root, v)

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


def compute_rftq_score(ces_mean, csc_score, structural_health, rlpc_score=None, judge_score=None):
    """
    RFTQ quality score:
      0.30 CES + 0.20 CSC + 0.25 RLPC + 0.15 LLM-judge + 0.10 Structural
    Falls back to the older 0.4/0.3/0.3 formula when rlpc_score is None for
    backward compatibility with early logs.
    judge_score is normalized 0-1 (rating/5). If None, weight is redistributed to CES.
    """
    chain_penalty = min(structural_health.get("chain_count", 0) * 0.05, 0.3)
    cv_penalty = min(structural_health.get("branching_cv", 0) * 0.2, 0.3)
    struct_score = max(0, 1.0 - chain_penalty - cv_penalty)

    if rlpc_score is None:
        rftq = 0.4 * max(ces_mean, 0) + 0.3 * max(csc_score, 0) + 0.3 * struct_score
        return float(rftq)

    if judge_score is None:
        rftq = (
            0.45 * max(ces_mean, 0)
            + 0.20 * max(csc_score, 0)
            + 0.25 * max(rlpc_score, 0)
            + 0.10 * struct_score
        )
    else:
        rftq = (
            0.30 * max(ces_mean, 0)
            + 0.20 * max(csc_score, 0)
            + 0.25 * max(rlpc_score, 0)
            + 0.15 * max(judge_score, 0)
            + 0.10 * struct_score
        )
    return float(rftq)


def compute_all_metrics(G_current, G_previous=None, embedder=None, with_rlpc=True, with_judge=False):
    """
    Compute all reference-free metrics.

    Args:
        G_current: networkx DiGraph of current taxonomy
        G_previous: networkx DiGraph of previous iteration (or None)
        embedder: SentenceTransformer (loaded automatically if None)
        with_rlpc: include Root-to-Leaf Path Coherence (RFTQ)
        with_judge: include LLM-as-judge (requires OPENAI_API_KEY)

    Returns:
        dict with all metrics
    """
    if embedder is None:
        embedder = _get_embedder()

    ces = compute_ces(G_current, embedder)
    csc = compute_csc(G_current, embedder)
    nted = compute_nted_proxy(G_current, G_previous)
    structural = compute_structural_health(G_current)

    rlpc = None
    rlpc_score_val = None
    if with_rlpc:
        try:
            from path_coherence import compute_path_coherence
            rlpc = compute_path_coherence(G_current, embedder=embedder, with_judge=with_judge)
            rlpc_score_val = rlpc["rlpc_score"]
        except Exception as e:
            rlpc = {"error": str(e)}

    judge_score_val = None
    if rlpc and with_judge and "llm_judge" in rlpc:
        j = rlpc["llm_judge"]
        if j.get("judge_mean") is not None:
            judge_score_val = j["judge_mean"] / 5.0

    rftq_d = compute_rftq_score(
        ces["ces_mean"],
        csc["csc_score"],
        structural,
        rlpc_score=rlpc_score_val,
        judge_score=judge_score_val,
    )

    out = {
        "ces": ces,
        "nliv": ces,
        "csc": csc,
        "nted": nted,
        "structural": structural,
        "rftq_d": rftq_d,
    }
    if rlpc is not None:
        out["rlpc"] = rlpc
    return out


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
        output = {
            "ces_mean": metrics["ces"]["ces_mean"],
            "ces_min": metrics["ces"]["ces_min"],
            "nliv_mean": metrics["ces"]["nliv_mean"],
            "nliv_min": metrics["ces"]["nliv_min"],
            "weak_edges_count": len(metrics["ces"]["weak_edges"]),
            "csc_score": metrics["csc"]["csc_score"],
            "csc_p_value": metrics["csc"]["p_value"],
            "nted": metrics["nted"]["nted"],
            "edges_added": metrics["nted"]["edges_added"],
            "edges_removed": metrics["nted"]["edges_removed"],
            "rftq_d": metrics["rftq_d"],
            **{k: v for k, v in metrics["structural"].items() if k != "chain_nodes"},
        }
        if "rlpc" in metrics and "rlpc_score" in metrics["rlpc"]:
            r = metrics["rlpc"]
            output["rlpc_score"] = r["rlpc_score"]
            output["rlpc_mono"] = r["monotonicity"]["mono_mean_score"]
            output["rlpc_step"] = r["step_coherence"]["step_mean"]
            output["rlpc_path_nli"] = r["path_nli"]["path_nli_mean"]
        print(json.dumps(output, indent=2))
    else:
        print("=" * 60)
        print("REFERENCE-FREE TAXONOMY METRICS")
        print("=" * 60)
        print()
        s = metrics["structural"]
        print(f"Nodes: {s['node_count']}  Edges: {s['edge_count']}  "
              f"Leaves: {s['leaf_count']}  Max depth: {s['max_depth']}")
        print()
        print("--- CES (Cosine Edge Score; legacy key: nliv_mean) ---")
        print(f"  Mean:  {metrics['ces']['ces_mean']:.4f}")
        print(f"  Min:   {metrics['ces']['ces_min']:.4f}")
        weak = metrics["ces"]["weak_edges"]
        print(f"  Weak edges (CES < 0.3): {len(weak)}")
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
        if "rlpc" in metrics and "rlpc_score" in metrics["rlpc"]:
            r = metrics["rlpc"]
            print("--- RLPC (Root-to-Leaf Path Coherence) ---")
            print(f"  Score:      {r['rlpc_score']:.4f}")
            print(f"  Mono:       {r['monotonicity']['mono_mean_score']:.3f}")
            print(f"  Step:       {r['step_coherence']['step_mean']:.3f}")
            print(f"  Path NLI:   {r['path_nli']['path_nli_mean']:.3f}")
            print()
        print(f"{'=' * 60}")
        print(f"RFTQ-D SCORE: {metrics['rftq_d']:.4f}")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
