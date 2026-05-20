#!/usr/bin/env python3
"""
convergence.py — Check if taxonomy construction has converged.

Reads output/hook_metrics.jsonl and checks for:
1. Quality plateau: RFTQ-D unchanged (±0.005) for 5+ iterations
2. All stories done: prd.json all passes=true

Returns JSON: {"stop": bool, "reason": str}
"""

import json
import sys
from pathlib import Path


def check_convergence():
    prd_file = Path("prd.json")
    if prd_file.exists():
        prd = json.loads(prd_file.read_text())
        stories = prd.get("userStories", [])
        if stories and all(s.get("passes", False) for s in stories):
            return {"stop": True, "reason": "All stories completed"}

    metrics_file = Path("output/hook_metrics.jsonl")
    if metrics_file.exists():
        lines = metrics_file.read_text().strip().split("\n")
        rftq_values = []
        for line in lines[-10:]:
            try:
                entry = json.loads(line)
                value = entry.get("rftq_d")
                if value and value != "N/A":
                    rftq_values.append(float(value))
            except (json.JSONDecodeError, ValueError):
                continue

        if len(rftq_values) >= 5:
            recent = rftq_values[-5:]
            spread = max(recent) - min(recent)
            if spread < 0.005:
                return {"stop": True, "reason": f"Quality plateau (spread={spread:.4f} over 5 iterations)"}

    return {"stop": False, "reason": ""}


if __name__ == "__main__":
    result = check_convergence()
    print(json.dumps(result))
