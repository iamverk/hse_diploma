#!/usr/bin/env python3
"""
convergence.py — Check if taxonomy construction has converged.

Reads output/hook_metrics.jsonl and checks for:
1. Quality plateau: composite unchanged (±0.005) for 5+ iterations
2. All stories done: prd.json all passes=true

Returns JSON: {"stop": bool, "reason": str}
"""

import json
import sys
from pathlib import Path


def check_convergence():
    # Check if all stories pass
    prd_file = Path("prd.json")
    if prd_file.exists():
        prd = json.loads(prd_file.read_text())
        stories = prd.get("userStories", [])
        if stories and all(s.get("passes", False) for s in stories):
            return {"stop": True, "reason": "All stories completed"}

    # Check for quality plateau in metrics log
    metrics_file = Path("output/hook_metrics.jsonl")
    if metrics_file.exists():
        lines = metrics_file.read_text().strip().split("\n")
        composites = []
        for line in lines[-10:]:  # Last 10 entries
            try:
                entry = json.loads(line)
                comp = entry.get("composite")
                if comp and comp != "N/A":
                    composites.append(float(comp))
            except (json.JSONDecodeError, ValueError):
                continue

        if len(composites) >= 5:
            recent = composites[-5:]
            spread = max(recent) - min(recent)
            if spread < 0.005:
                return {"stop": True, "reason": f"Quality plateau (spread={spread:.4f} over 5 iterations)"}

    return {"stop": False, "reason": ""}


if __name__ == "__main__":
    result = check_convergence()
    print(json.dumps(result))
