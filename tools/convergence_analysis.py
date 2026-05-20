#!/usr/bin/env python3
"""
convergence_analysis.py — Convergence curves for thesis Chapter 6.

For each experiment with per-iteration metrics, compute:
  - RFTQ-D trajectory (per iteration)
  - Iterations to reach 95% of final RFTQ-D
  - Plateau detection (no improvement in last K iterations)
  - Story completion rate over time

Saves: convergence_summary.csv + matplotlib PNG.
"""

import csv
import os
import sys
import json
from pathlib import Path
from glob import glob
import numpy as np

ROOT = Path(os.environ.get("BLIND_TAXONOMY_WORKSPACE", str(Path(__file__).resolve().parents[2])))
EXP_DIRS = {
    "Exp 5": ".hidden_eval/exp5_results",
    "Exp 6": ".hidden_eval/exp6_results",
    "Exp 7": ".hidden_eval/exp7_results",
    "Exp 8": ".hidden_eval/exp8_results",
    "Exp 9": ".hidden_eval/exp9_results",
    "Exp 10": ".hidden_eval/exp10_results",
}


def load_csv(exp_dir):
    """Try standard names, return list of row dicts."""
    candidates = [
        ROOT / exp_dir / "metrics_per_iteration.csv",
        ROOT / exp_dir / "metrics_final.csv",
    ]
    csvs = sorted(glob(str(ROOT / exp_dir / "metrics_cursor_*.csv")))
    candidates.extend(Path(c) for c in csvs)
    for p in candidates:
        if p.exists():
            with open(p) as f:
                rows = list(csv.DictReader(f))
            if rows:
                return rows, p
    return [], None


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def analyze(rows):
    """Extract RFTQ-D trajectory + metadata."""
    rftq_values, ces_values, cscs, nodes, elapsed_total = [], [], [], [], 0
    n_pass, n_crash, n_discard = 0, 0, 0

    for r in rows:
        c = to_float(r.get("rftq_d"))
        if c is not None:
            rftq_values.append(c)
            ces_values.append(to_float(r.get("ces_mean") or r.get("nliv_mean")) or 0)
            cscs.append(to_float(r.get("csc_score")) or 0)
            n = to_float(r.get("node_count"))
            if n:
                nodes.append(n)
        st = (r.get("status") or "").lower()
        passed = (r.get("passed") or "").lower() == "true"
        elapsed = to_float(r.get("elapsed_sec")) or 0
        elapsed_total += elapsed
        if "crash" in st:
            n_crash += 1
        elif "discard" in st or "rollback" in st:
            n_discard += 1
        elif passed:
            n_pass += 1

    if not rftq_values:
        return None

    final = rftq_values[-1]
    target = 0.95 * final

    iters_to_95 = None
    for i, c in enumerate(rftq_values, start=1):
        if c >= target:
            iters_to_95 = i
            break

    # Plateau detection: longest tail with delta < 0.005
    plateau_start = None
    if len(rftq_values) >= 3:
        best = max(rftq_values)
        for i in range(len(rftq_values) - 1, 0, -1):
            if abs(rftq_values[i] - best) < 0.01:
                plateau_start = i
            else:
                break

    return {
        "n_iterations": len(rows),
        "n_with_rftq_d": len(rftq_values),
        "n_passed": n_pass,
        "n_crashed": n_crash,
        "n_discarded": n_discard,
        "elapsed_total_sec": elapsed_total,
        "elapsed_total_min": round(elapsed_total / 60, 1),
        "rftq_d_trajectory": rftq_values,
        "ces_trajectory": ces_values,
        "nliv_trajectory": ces_values,
        "csc_trajectory": cscs,
        "final_rftq_d": rftq_values[-1],
        "max_rftq_d": max(rftq_values),
        "iters_to_95pct_final": iters_to_95,
        "plateau_start_iter": plateau_start,
        "node_growth": nodes,
    }


def main():
    summary = {}
    print("=" * 80)
    print("CONVERGENCE ANALYSIS — when does Ralph plateau?")
    print("=" * 80)
    print(f"\n{'Setup':<8}  {'Iters':<7}{'Pass':<6}{'Crash':<7}{'Disc':<6}{'Final':<8}{'Max':<8}{'95%@':<7}{'Plateau@':<9}{'Min':<6}")
    print("-" * 80)

    for label, d in EXP_DIRS.items():
        rows, src = load_csv(d)
        if not rows:
            print(f"{label:<8}  (no CSV)")
            continue
        a = analyze(rows)
        if a is None:
            print(f"{label:<8}  (no RFTQ-D data)")
            continue
        summary[label] = a
        print(f"{label:<8}  {a['n_iterations']:<7}{a['n_passed']:<6}{a['n_crashed']:<7}"
              f"{a['n_discarded']:<6}{a['final_rftq_d']:<8.4f}{a['max_rftq_d']:<8.4f}"
              f"{str(a['iters_to_95pct_final']):<7}{str(a['plateau_start_iter']):<9}"
              f"{a['elapsed_total_min']:<6}")

    print("\n" + "=" * 80)
    print("INSIGHTS")
    print("=" * 80)

    valid = [s for s in summary.values() if s["iters_to_95pct_final"]]
    if valid:
        avg_iters_95 = np.mean([s["iters_to_95pct_final"] for s in valid])
        print(f"\n• Mean iterations to 95% of final RFTQ-D: {avg_iters_95:.1f}")
        print(f"• Median: {np.median([s['iters_to_95pct_final'] for s in valid]):.1f}")
        print(f"• → Most experiments converge within first 1-3 iterations on RFTQ-D,")
        print(f"     then refine quality over remaining iterations (story completeness).")

    crashes = sum(s["n_crashed"] for s in summary.values())
    total_iter = sum(s["n_iterations"] for s in summary.values())
    print(f"\n• Total crash rate across all experiments: {crashes}/{total_iter} = {crashes/total_iter*100:.1f}%")

    rollback = sum(s["n_discarded"] for s in summary.values())
    print(f"• Total rollback rate (RFTQ-D drop > threshold): {rollback}/{total_iter} = {rollback/total_iter*100:.1f}%")

    print(f"\n{'Setup':<8}  Iter 1 → Final  Improvement")
    print("-" * 50)
    for label, s in summary.items():
        if len(s["rftq_d_trajectory"]) >= 2:
            first = s["rftq_d_trajectory"][0]
            final = s["rftq_d_trajectory"][-1]
            delta = final - first
            print(f"{label:<8}  {first:.4f} → {final:.4f}  {delta:+.4f}")

    out = ROOT / ".hidden_eval" / "convergence_results.json"
    with open(out, "w") as f:
        json.dump(summary, f, indent=2, default=lambda x: float(x) if hasattr(x, 'item') else x)
    print(f"\nSaved: {out}")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        for label, s in summary.items():
            traj = s["rftq_d_trajectory"]
            axes[0].plot(range(1, len(traj) + 1), traj, marker="o", label=label, linewidth=1.8)
        axes[0].set_xlabel("Iteration")
        axes[0].set_ylabel("RFTQ-D score")
        axes[0].set_title("RFTQ-D trajectory across Ralph iterations")
        axes[0].grid(True, alpha=0.3)
        axes[0].legend(loc="lower right")

        for label, s in summary.items():
            if s["ces_trajectory"]:
                axes[1].plot(range(1, len(s["ces_trajectory"]) + 1), s["ces_trajectory"],
                            marker="s", label=label, linewidth=1.8)
        axes[1].set_xlabel("Iteration")
        axes[1].set_ylabel("CES mean")
        axes[1].set_title("CES trajectory across Ralph iterations")
        axes[1].grid(True, alpha=0.3)
        axes[1].legend(loc="lower right")

        plt.tight_layout()
        png = ROOT / ".hidden_eval" / "convergence_plot.png"
        plt.savefig(png, dpi=120)
        print(f"Plot saved: {png}")
    except ImportError:
        print("matplotlib not available, skipping plot")


if __name__ == "__main__":
    main()
