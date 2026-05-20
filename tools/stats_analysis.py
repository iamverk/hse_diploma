#!/usr/bin/env python3
"""
stats_analysis.py — Statistical significance + sensitivity analysis for thesis.

Performs:
  A. Bootstrap 95% CI for CES (per edge) and Judge (per path) on each experiment.
     Permutation tests for pairwise comparisons.
  B. Sensitivity of RFTQ ranking under 5 alternative weight schemes.

Usage:
    python tools/stats_analysis.py
"""

import json
import os
import sys
import numpy as np
import networkx as nx
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from taxonomy_core import load_taxonomy, _taxonomy_to_graph
from path_coherence import _node_name

EXPERIMENTS = {
    "Exp 1":  ".hidden_eval/exp1_results",
    "Exp 5":  ".hidden_eval/exp5_results",
    "Exp 6":  ".hidden_eval/exp6_results",
    "Exp 7":  ".hidden_eval/exp7_results",
    "Exp 8":  ".hidden_eval/exp8_results",
    "Exp 9":  ".hidden_eval/exp9_results",
    "Exp 10": ".hidden_eval/exp10_results",
    "Naive":  ".hidden_eval/naive_baseline_results",
}

ROOT = Path(os.environ.get("BLIND_TAXONOMY_WORKSPACE", str(Path(__file__).resolve().parents[2])))
RNG = np.random.default_rng(42)


def load_taxonomy_path(exp_dir):
    for fname in ["final_taxonomy.json", "taxonomy_final.json", "taxonomy.json", "taxonomy_naive_inline.json"]:
        p = ROOT / exp_dir / fname
        if p.exists():
            return p
    return None


def compute_ces_per_edge(G):
    """Return list of cosine scores for each edge using sentence-transformer."""
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer('all-MiniLM-L6-v2')
    edges = list(G.edges())
    if not edges:
        return []
    names = list(set(_node_name(G, n) for n in G.nodes()))
    name_to_idx = {n: i for i, n in enumerate(names)}
    emb = model.encode(names, normalize_embeddings=True)
    scores = []
    for u, v in edges:
        a = emb[name_to_idx[_node_name(G, u)]]
        b = emb[name_to_idx[_node_name(G, v)]]
        scores.append(float(np.dot(a, b)))
    return scores


def bootstrap_ci(data, n=10000, ci=95):
    """Return mean and (lo, hi) 95% CI by bootstrap."""
    if not data:
        return 0.0, (0.0, 0.0)
    arr = np.asarray(data)
    means = []
    for _ in range(n):
        sample = RNG.choice(arr, size=len(arr), replace=True)
        means.append(sample.mean())
    lo = np.percentile(means, (100 - ci) / 2)
    hi = np.percentile(means, 100 - (100 - ci) / 2)
    return float(arr.mean()), (float(lo), float(hi))


def permutation_test(a, b, n=10000):
    """Two-sided permutation test on difference of means. Returns p-value."""
    a, b = np.asarray(a), np.asarray(b)
    obs = abs(a.mean() - b.mean())
    combined = np.concatenate([a, b])
    n_a = len(a)
    count = 0
    for _ in range(n):
        RNG.shuffle(combined)
        diff = abs(combined[:n_a].mean() - combined[n_a:].mean())
        if diff >= obs:
            count += 1
    return (count + 1) / (n + 1)


def run_part_A():
    print("=" * 76)
    print("A. STATISTICAL SIGNIFICANCE — bootstrap CI + permutation tests")
    print("=" * 76)

    ces_data = {}
    judge_data = {}

    for label, exp_dir in EXPERIMENTS.items():
        jp = ROOT / exp_dir / "judge_ratings.json"
        if jp.exists():
            ratings = [r["rating"] for r in json.load(open(jp))["ratings"]]
            judge_data[label] = ratings

        tp = load_taxonomy_path(exp_dir)
        if tp:
            G = _taxonomy_to_graph(load_taxonomy(tp))
            ces_data[label] = compute_ces_per_edge(G)

    print(f"\n{'Setup':<10}  {'CES mean (95% CI)':<25}  {'Judge mean (95% CI)':<25}")
    print("-" * 70)
    for label in EXPERIMENTS:
        if label in ces_data:
            n_mean, (n_lo, n_hi) = bootstrap_ci(ces_data[label])
            n_str = f"{n_mean:.3f} [{n_lo:.3f}, {n_hi:.3f}]"
        else:
            n_str = "—"
        if label in judge_data:
            j_mean, (j_lo, j_hi) = bootstrap_ci(judge_data[label])
            j_str = f"{j_mean:.2f} [{j_lo:.2f}, {j_hi:.2f}]"
        else:
            j_str = "—"
        print(f"{label:<10}  {n_str:<25}  {j_str:<25}")

    pairs = [
        ("Exp 7", "Naive"),
        ("Exp 10", "Naive"),
        ("Exp 7", "Exp 10"),
        ("Exp 7", "Exp 9"),
        ("Exp 10", "Exp 9"),
        ("Exp 8", "Exp 7"),
    ]
    print(f"\n{'Pair':<22}  {'CES p':<10}  {'Judge p':<10}  {'CES Δ':<10}  {'Judge Δ':<10}")
    print("-" * 70)
    results = {}
    for a, b in pairs:
        p_ces = permutation_test(ces_data[a], ces_data[b]) if a in ces_data and b in ces_data else None
        p_judge = permutation_test(judge_data[a], judge_data[b]) if a in judge_data and b in judge_data else None
        delta_ces = np.mean(ces_data[a]) - np.mean(ces_data[b]) if a in ces_data and b in ces_data else None
        delta_j = np.mean(judge_data[a]) - np.mean(judge_data[b]) if a in judge_data and b in judge_data else None
        sig_ces = "***" if p_ces and p_ces < 0.001 else "**" if p_ces and p_ces < 0.01 else "*" if p_ces and p_ces < 0.05 else "ns"
        sig_j = "***" if p_judge and p_judge < 0.001 else "**" if p_judge and p_judge < 0.01 else "*" if p_judge and p_judge < 0.05 else "ns"
        print(f"{a} vs {b:<12}  {p_ces:.4f} {sig_ces:<3}  {p_judge:.4f} {sig_j:<3}  {delta_ces:+.3f}    {delta_j:+.3f}")
        results[f"{a} vs {b}"] = {
            "ces_p": p_ces, "ces_delta": delta_ces,
            "judge_p": p_judge, "judge_delta": delta_j,
        }
    return {"ces_data": {k: list(v) for k, v in ces_data.items()},
            "judge_data": judge_data,
            "pairwise": results}


WEIGHT_SCHEMES = {
    "v2 (default)": (0.30, 0.20, 0.25, 0.15, 0.10),  # CES, CSC, RLPC, Judge, Struct
    "Equal":        (0.25, 0.25, 0.25, 0.25, 0.00),
    "CES-heavy":    (0.50, 0.15, 0.15, 0.15, 0.05),
    "CSC-heavy":    (0.15, 0.50, 0.15, 0.15, 0.05),
    "RLPC-heavy":   (0.15, 0.15, 0.50, 0.15, 0.05),
    "Judge-heavy":  (0.15, 0.15, 0.15, 0.50, 0.05),
    "No-Judge":     (0.45, 0.20, 0.25, 0.00, 0.10),
}

METRICS_TABLE = {
    "Exp 1":  (0.507, 0.312, 0.725, 4.28, 1.0),
    "Exp 5":  (0.572, 0.427, 0.717, 4.46, 1.0),
    "Exp 6":  (0.567, 0.314, 0.749, 3.82, 1.0),
    "Exp 7":  (0.620, 0.491, 0.761, 4.64, 1.0),
    "Exp 8":  (0.625, 0.410, 0.744, 4.44, 1.0),
    "Exp 9":  (0.660, 0.301, 0.767, 3.74, 1.0),
    "Exp 10": (0.599, 0.459, 0.745, 4.74, 0.912),  # cv=0.44
    "Naive":  (0.535, 0.236, 0.707, 4.66, 0.898),  # cv=0.51
}


def run_part_B():
    print("\n" + "=" * 76)
    print("B. SENSITIVITY ANALYSIS — does ranking change under different weights?")
    print("=" * 76)

    rankings = {}
    print(f"\n{'Setup':<10} ", end="")
    for scheme in WEIGHT_SCHEMES:
        print(f"{scheme:<14}", end="")
    print()
    print("-" * (10 + 14 * len(WEIGHT_SCHEMES)))

    scores_by_scheme = {}
    for scheme, (w_n, w_c, w_r, w_j, w_s) in WEIGHT_SCHEMES.items():
        scheme_scores = {}
        for label, (n, c, r, j, s) in METRICS_TABLE.items():
            score = w_n * n + w_c * c + w_r * r + w_j * (j / 5.0) + w_s * s
            scheme_scores[label] = score
        scores_by_scheme[scheme] = scheme_scores

    for label in METRICS_TABLE:
        print(f"{label:<10} ", end="")
        for scheme in WEIGHT_SCHEMES:
            score = scores_by_scheme[scheme][label]
            print(f"{score:<14.4f}", end="")
        print()

    print(f"\n{'Scheme':<14}  Ranking (best → worst)")
    print("-" * 76)
    for scheme in WEIGHT_SCHEMES:
        ordered = sorted(scores_by_scheme[scheme].items(), key=lambda x: -x[1])
        ranks = " > ".join(name for name, _ in ordered)
        print(f"{scheme:<14}  {ranks}")
        rankings[scheme] = [name for name, _ in ordered]

    n_top1_exp7 = sum(1 for r in rankings.values() if r[0] == "Exp 7")
    n_naive_last = sum(1 for r in rankings.values() if r[-1] == "Naive")
    print(f"\nRobustness checks:")
    print(f"  Exp 7 ranks #1 in {n_top1_exp7}/{len(rankings)} schemes")
    print(f"  Naive ranks last in {n_naive_last}/{len(rankings)} schemes")

    top3_sets = [set(r[:3]) for r in rankings.values()]
    common_top3 = set.intersection(*top3_sets)
    print(f"  Common top-3 across all schemes: {sorted(common_top3)}")

    return {"rankings": rankings, "scores": scores_by_scheme,
            "exp7_top1_count": n_top1_exp7, "naive_last_count": n_naive_last,
            "common_top3": list(common_top3)}


def main():
    out_a = run_part_A()
    out_b = run_part_B()
    out = {"part_A": out_a, "part_B": out_b}
    out_path = ROOT / ".hidden_eval" / "stats_results.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=lambda x: float(x) if isinstance(x, np.floating) else x)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
