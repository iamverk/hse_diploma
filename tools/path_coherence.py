#!/usr/bin/env python3
"""
path_coherence.py — Root-to-Leaf Path Coherence (RLPC) metrics.

Reference-free metrics that evaluate whether each full root→leaf path
is semantically coherent as a taxonomic chain (general → specific).

Three sub-metrics:
  1. Monotonicity   — does similarity-to-root decay monotonically along path?
  2. Step coherence — mean cosine(parent_i, child_i) across the path
  3. Path NLI proxy — embedding similarity between concatenated path text
                      and synthetic IS-A sentence

Usage:
    python tools/path_coherence.py taxonomy.json
    python tools/path_coherence.py taxonomy.json --json
    python tools/path_coherence.py taxonomy.json --judge
"""

import json
import os
import sys
import numpy as np
import networkx as nx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from taxonomy_core import load_taxonomy, _taxonomy_to_graph
from metrics_v2 import _get_embedder, _node_name


def extract_root_leaf_paths(G):
    """Return list of paths (each a list of node ids) from root to every leaf."""
    roots = [n for n in G.nodes() if G.in_degree(n) == 0]
    if not roots:
        return []
    root = roots[0]
    leaves = [n for n in G.nodes() if G.out_degree(n) == 0]
    paths = []
    for leaf in leaves:
        try:
            path = nx.shortest_path(G, root, leaf)
            if len(path) >= 2:
                paths.append(path)
        except nx.NetworkXNoPath:
            continue
    return paths


def _path_names(G, path):
    return [_node_name(G, n) for n in path]


def compute_monotonicity(G, paths, embeddings_by_id):
    """
    For each path, check if cosine(node_i, root) strictly decreases.
    Returns ratio of strictly monotone paths and mean Kendall-tau-like score.
    """
    if not paths:
        return {"mono_ratio": 0.0, "mono_mean_score": 0.0, "violations": []}

    monotone_count = 0
    scores = []
    violations = []

    for path in paths:
        if len(path) < 3:
            monotone_count += 1
            scores.append(1.0)
            continue
        root_emb = embeddings_by_id[path[0]]
        sims = [float(np.dot(root_emb, embeddings_by_id[n])) for n in path]

        pairs = list(zip(sims[:-1], sims[1:]))
        strictly_decreasing = sum(1 for a, b in pairs if b < a - 1e-6)
        score = strictly_decreasing / len(pairs)
        scores.append(score)

        if score == 1.0:
            monotone_count += 1
        else:
            violations.append({
                "path": _path_names(G, path),
                "sims": [round(s, 3) for s in sims],
                "score": round(score, 3),
            })

    violations.sort(key=lambda v: v["score"])

    return {
        "mono_ratio": monotone_count / len(paths),
        "mono_mean_score": float(np.mean(scores)),
        "violations": violations[:10],
        "n_paths": len(paths),
    }


def compute_step_coherence(G, paths, embeddings_by_id):
    """
    For each path, compute mean cosine(parent_i, child_i) across all consecutive pairs.
    Aggregate by mean and min over paths.
    """
    if not paths:
        return {"step_mean": 0.0, "step_min": 0.0, "weak_paths": []}

    path_scores = []
    weak_paths = []

    for path in paths:
        if len(path) < 2:
            continue
        sims = [
            float(np.dot(embeddings_by_id[path[i]], embeddings_by_id[path[i + 1]]))
            for i in range(len(path) - 1)
        ]
        mean_sim = float(np.mean(sims))
        path_scores.append(mean_sim)
        if mean_sim < 0.4:
            weak_paths.append({
                "path": _path_names(G, path),
                "step_mean": round(mean_sim, 3),
                "min_step": round(float(np.min(sims)), 3),
            })

    weak_paths.sort(key=lambda v: v["step_mean"])

    return {
        "step_mean": float(np.mean(path_scores)) if path_scores else 0.0,
        "step_min": float(np.min(path_scores)) if path_scores else 0.0,
        "weak_paths": weak_paths[:10],
        "n_paths": len(path_scores),
    }


def compute_path_nli(G, paths, embedder):
    """
    For each path [a, b, c, d], encode an IS-A sentence
    "d is a kind of c which is a kind of b which is a kind of a"
    and compare to the literal path concatenation. Higher cos = more
    natural-language-coherent path.
    """
    if not paths:
        return {"path_nli_mean": 0.0, "path_nli_min": 0.0}

    sentences_isa = []
    sentences_concat = []

    for path in paths:
        names = _path_names(G, path)
        rev = list(reversed(names))
        if len(rev) >= 2:
            isa = rev[0] + "".join(f" is a kind of {x}" for x in rev[1:])
        else:
            isa = rev[0]
        concat = " > ".join(names)
        sentences_isa.append(isa)
        sentences_concat.append(concat)

    emb_isa = embedder.encode(sentences_isa, normalize_embeddings=True)
    emb_concat = embedder.encode(sentences_concat, normalize_embeddings=True)

    sims = [float(np.dot(a, b)) for a, b in zip(emb_isa, emb_concat)]

    return {
        "path_nli_mean": float(np.mean(sims)),
        "path_nli_min": float(np.min(sims)),
        "n_paths": len(sims),
    }


def compute_llm_judge(G, paths, sample_size=50, model=None):
    """
    Optional: ask LLM to rate each path 1-5 for taxonomic validity.
    Requires OPENAI_API_KEY. Uses OPENAI_JUDGE_MODEL when set.
    """
    model = model or os.environ.get("OPENAI_JUDGE_MODEL", "gpt-5.5")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {"skipped": "OPENAI_API_KEY not set", "judge_mean": None}
    try:
        from openai import OpenAI
    except ImportError:
        return {"skipped": "openai package not installed", "judge_mean": None}

    import random
    random.seed(42)
    sampled = paths if len(paths) <= sample_size else random.sample(paths, sample_size)
    client = OpenAI(api_key=api_key)

    ratings = []
    invalid_paths = []

    for path in sampled:
        names = _path_names(G, path)
        path_str = " → ".join(names)
        prompt = (
            f"Rate this taxonomic path from general to specific (1=invalid, 5=perfect IS-A chain). "
            f"Reply with ONLY a single digit 1-5.\n\nPath: {path_str}"
        )
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4,
                temperature=0,
            )
            text = resp.choices[0].message.content.strip()
            rating = int(text[0])
            ratings.append(rating)
            if rating <= 2:
                invalid_paths.append({"path": names, "rating": rating})
        except Exception as e:
            continue

    if not ratings:
        return {"skipped": "no successful calls", "judge_mean": None}

    return {
        "judge_mean": float(np.mean(ratings)),
        "judge_n": len(ratings),
        "judge_pct_valid": float(sum(1 for r in ratings if r >= 4) / len(ratings)),
        "invalid_paths": invalid_paths[:10],
        "model": model,
    }


def compute_rlpc_score(mono, step, nli):
    """RLPC aggregation: weighted mean of three path submetrics."""
    w_mono = 0.35
    w_step = 0.40
    w_nli = 0.25
    return float(
        w_mono * mono["mono_mean_score"]
        + w_step * step["step_mean"]
        + w_nli * nli["path_nli_mean"]
    )


def compute_path_coherence(G, embedder=None, with_judge=False):
    """Top-level entry point — compute all path coherence metrics."""
    if embedder is None:
        embedder = _get_embedder()

    paths = extract_root_leaf_paths(G)

    all_ids = list(G.nodes())
    names = [_node_name(G, n) for n in all_ids]
    emb_matrix = embedder.encode(names, normalize_embeddings=True)
    embeddings_by_id = {nid: emb_matrix[i] for i, nid in enumerate(all_ids)}

    mono = compute_monotonicity(G, paths, embeddings_by_id)
    step = compute_step_coherence(G, paths, embeddings_by_id)
    nli = compute_path_nli(G, paths, embedder)
    rlpc = compute_rlpc_score(mono, step, nli)

    result = {
        "rlpc_score": rlpc,
        "monotonicity": mono,
        "step_coherence": step,
        "path_nli": nli,
        "n_paths": len(paths),
        "mean_path_length": float(np.mean([len(p) for p in paths])) if paths else 0.0,
    }

    if with_judge:
        result["llm_judge"] = compute_llm_judge(G, paths)

    return result


def main():
    args = sys.argv[1:]
    json_out = "--json" in args
    with_judge = "--judge" in args
    paths_arg = [a for a in args if not a.startswith("--")]

    taxonomy_path = paths_arg[0] if paths_arg else "taxonomy.json"
    if not os.path.exists(taxonomy_path):
        print(f"ERROR: {taxonomy_path} not found", file=sys.stderr)
        sys.exit(1)

    tax = load_taxonomy(taxonomy_path)
    G = _taxonomy_to_graph(tax)
    result = compute_path_coherence(G, with_judge=with_judge)

    if json_out:
        slim = {
            "rlpc_score": result["rlpc_score"],
            "n_paths": result["n_paths"],
            "mean_path_length": result["mean_path_length"],
            "mono_ratio": result["monotonicity"]["mono_ratio"],
            "mono_mean_score": result["monotonicity"]["mono_mean_score"],
            "step_mean": result["step_coherence"]["step_mean"],
            "step_min": result["step_coherence"]["step_min"],
            "path_nli_mean": result["path_nli"]["path_nli_mean"],
            "path_nli_min": result["path_nli"]["path_nli_min"],
        }
        if with_judge:
            slim["llm_judge"] = result.get("llm_judge", {})
        print(json.dumps(slim, indent=2))
        return

    print("=" * 60)
    print(f"ROOT-TO-LEAF PATH COHERENCE — {taxonomy_path}")
    print("=" * 60)
    print(f"Paths: {result['n_paths']}  Mean length: {result['mean_path_length']:.2f}")
    print()
    print("--- Monotonicity (specificity decreases toward leaf) ---")
    m = result["monotonicity"]
    print(f"  Strict ratio:       {m['mono_ratio']:.3f}")
    print(f"  Mean score:         {m['mono_mean_score']:.3f}")
    if m["violations"]:
        print(f"  Top violations:")
        for v in m["violations"][:3]:
            print(f"    {' → '.join(v['path'])}  (score {v['score']})")
    print()
    print("--- Step Coherence (parent↔child along path) ---")
    s = result["step_coherence"]
    print(f"  Mean:               {s['step_mean']:.3f}")
    print(f"  Min path:           {s['step_min']:.3f}")
    if s["weak_paths"]:
        print(f"  Weak paths:")
        for w in s["weak_paths"][:3]:
            print(f"    {' → '.join(w['path'])}  (mean {w['step_mean']})")
    print()
    print("--- Path NLI (IS-A sentence vs path concat) ---")
    n = result["path_nli"]
    print(f"  Mean:               {n['path_nli_mean']:.3f}")
    print(f"  Min:                {n['path_nli_min']:.3f}")
    print()
    if with_judge and "llm_judge" in result:
        j = result["llm_judge"]
        print("--- LLM-as-judge (1-5) ---")
        if "skipped" in j:
            print(f"  Skipped: {j['skipped']}")
        else:
            print(f"  Mean rating:        {j['judge_mean']:.2f}")
            print(f"  % valid (≥4):       {j['judge_pct_valid']*100:.1f}%")
            print(f"  Sampled:            {j['judge_n']} paths")
        print()
    print("=" * 60)
    print(f"RLPC SCORE:           {result['rlpc_score']:.4f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
