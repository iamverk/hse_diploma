#!/usr/bin/env python3
"""
check_edge.py — CLI tool to check IS-A edge quality (CES) before adding.

Usage:
    python tools/check_edge.py "Electronics" "Headphones"
    python tools/check_edge.py --batch '[{"parent":"A","child":"B"},...]'
    python tools/check_edge.py --interactive
    > Electronics|Headphones
    > Electronics|Dog Food
    > (empty line or Ctrl+D to exit)

Returns JSON with CES score and verdict. The legacy `nliv` key is kept for old scripts.
"""

import sys
import json
import warnings
import os

warnings.filterwarnings("ignore")
os.environ["TOKENIZERS_PARALLELISM"] = "false"


def _get_embedder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("all-MiniLM-L6-v2")


def check_one(parent, child, embedder):
    import numpy as np
    p = embedder.encode(parent, normalize_embeddings=True)
    c = embedder.encode(child, normalize_embeddings=True)
    ces = float(np.dot(p, c))

    if ces >= 0.5:
        verdict = "EXCELLENT"
    elif ces >= 0.4:
        verdict = "GOOD"
    elif ces >= 0.3:
        verdict = "WEAK"
    else:
        verdict = "BAD"

    score = round(ces, 4)
    return {"parent": parent, "child": child, "ces": score, "nliv": score, "verdict": verdict}


def main():
    if len(sys.argv) < 2:
        print("Usage: python tools/check_edge.py <parent> <child>")
        print("       python tools/check_edge.py --batch '<json array>'")
        print("       python tools/check_edge.py --interactive")
        sys.exit(1)

    embedder = _get_embedder()

    if sys.argv[1] == "--batch":
        edges = json.loads(sys.argv[2])
        results = [check_one(e["parent"], e["child"], embedder) for e in edges]
        results.sort(key=lambda x: x["ces"])
        good = sum(1 for r in results if r["verdict"] in ("EXCELLENT", "GOOD"))
        weak = sum(1 for r in results if r["verdict"] == "WEAK")
        bad = sum(1 for r in results if r["verdict"] == "BAD")
        print(json.dumps({"total": len(results), "good": good, "weak": weak, "bad": bad, "edges": results}, indent=2))

    elif sys.argv[1] == "--interactive":
        print("READY", flush=True)
        for line in sys.stdin:
            line = line.strip()
            if not line:
                break
            parts = line.split("|", 1)
            if len(parts) != 2:
                print(json.dumps({"error": "Format: parent|child"}), flush=True)
                continue
            result = check_one(parts[0].strip(), parts[1].strip(), embedder)
            print(json.dumps(result), flush=True)
    else:
        parent = sys.argv[1]
        child = sys.argv[2]
        result = check_one(parent, child, embedder)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
