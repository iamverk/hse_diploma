#!/usr/bin/env python3
"""
taxonomy_linter.py — Detect taxonomy anti-patterns programmatically.

Lints a taxonomy.json for:
  • Wrapper nodes (single-child internal that just rephrases parent)
  • Redundant name prefixes (child name starts with parent token)
  • Accessory misplacement (child contains 'accessor' / 'mount' / 'cover' /
                            'case' / 'charger' under non-accessory parent)
  • Activity-as-product (child is a verb/activity not a thing)
  • Brand-as-type (child is a known brand, e.g. iPhones, Samsung)
  • Self-similar parent-child (cosine > 0.95 — duplicate)
  • Weak edges (CES < threshold)
  • Mixed-domain children (siblings have very different embeddings)

Output: severity-tagged JSON report.

Usage:
    python tools/taxonomy_linter.py taxonomy.json
    python tools/taxonomy_linter.py taxonomy.json --json
    python tools/taxonomy_linter.py taxonomy.json --threshold 0.30
"""

import json
import os
import re
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from taxonomy_core import load_taxonomy, _taxonomy_to_graph
from metrics_v2 import _get_embedder, _node_name


ACCESSORY_PATTERNS = re.compile(
    r"\b(accessor|mount|cover|case|charger|adapter|cable|battery|batter|tip|holder|bag|pouch|lid|stand|strap|strapless|buckle|filter|grip|cleaner|wipe|spray)\b",
    re.IGNORECASE,
)

ACTIVITY_PATTERNS = re.compile(
    r"\b(running|hiking|cycling|fishing|hunting|skiing|surfing|swimming|reading|writing|painting|gaming|cooking|workout|renovation|sport|sports)\b",
    re.IGNORECASE,
)

BRAND_NAMES = {
    "iphone", "iphones", "samsung", "android", "apple", "sony", "lg",
    "nike", "adidas", "honda", "toyota", "ford", "philips", "bosch",
    "dyson", "kindle", "alexa", "echo", "fitbit", "garmin", "rolex",
    "playstation", "xbox", "nintendo", "switch",
}

ACCESSORY_PARENT_KEYWORDS = {
    "accessor", "supplies", "supply", "gear", "kit", "parts",
}


def lint_taxonomy(G, embedder=None, weak_threshold=0.30):
    if embedder is None:
        embedder = _get_embedder()
    issues = []

    nodes = list(G.nodes())
    names = {n: _node_name(G, n) for n in nodes}
    name_list = list(set(names.values()))
    name_to_idx = {nm: i for i, nm in enumerate(name_list)}
    emb = embedder.encode(name_list, normalize_embeddings=True)

    children_of = {n: list(G.successors(n)) for n in nodes}

    for n in nodes:
        n_name = names[n]
        kids = children_of[n]

        if len(kids) == 1 and G.in_degree(n) > 0:
            child_name = names[kids[0]]
            sim = float(np.dot(emb[name_to_idx[n_name]], emb[name_to_idx[child_name]]))
            if sim > 0.85:
                issues.append({
                    "severity": "warn",
                    "type": "wrapper_node",
                    "node": n_name,
                    "child": child_name,
                    "cosine": round(sim, 3),
                    "fix": f"Collapse '{n_name}' into its parent or merge with '{child_name}'.",
                })

        for c in kids:
            c_name = names[c]
            tokens_n = set(re.findall(r"\w+", n_name.lower()))
            tokens_c = re.findall(r"\w+", c_name.lower())
            if tokens_c and tokens_c[0] in tokens_n and len(tokens_c) > 1:
                issues.append({
                    "severity": "info",
                    "type": "redundant_prefix",
                    "parent": n_name,
                    "child": c_name,
                    "fix": f"Drop '{tokens_c[0]}' prefix from '{c_name}'.",
                })

        parent_lower = n_name.lower()
        parent_is_accessory = any(k in parent_lower for k in ACCESSORY_PARENT_KEYWORDS)
        if not parent_is_accessory:
            for c in kids:
                c_name = names[c]
                if ACCESSORY_PATTERNS.search(c_name) and not ACCESSORY_PATTERNS.search(n_name):
                    sim = float(np.dot(emb[name_to_idx[n_name]], emb[name_to_idx[c_name]]))
                    issues.append({
                        "severity": "error" if sim < 0.4 else "warn",
                        "type": "accessory_misplacement",
                        "parent": n_name,
                        "child": c_name,
                        "cosine": round(sim, 3),
                        "fix": f"Move '{c_name}' under an Accessories parent, not '{n_name}'.",
                    })

        for c in kids:
            c_name = names[c]
            if ACTIVITY_PATTERNS.search(c_name) and not ACTIVITY_PATTERNS.search(n_name):
                issues.append({
                    "severity": "info",
                    "type": "activity_as_product",
                    "parent": n_name,
                    "child": c_name,
                    "fix": f"'{c_name}' is an activity. Rename to '{c_name} Equipment' or '{c_name} Gear'.",
                })

        for c in kids:
            c_name_lower = names[c].lower()
            for brand in BRAND_NAMES:
                if re.search(r"\b" + brand + r"s?\b", c_name_lower):
                    issues.append({
                        "severity": "info",
                        "type": "brand_as_type",
                        "parent": n_name,
                        "child": names[c],
                        "brand": brand,
                        "fix": f"'{names[c]}' is a brand, not a product type. Consider attribute-level instead.",
                    })
                    break

        for c in kids:
            c_name = names[c]
            sim = float(np.dot(emb[name_to_idx[n_name]], emb[name_to_idx[c_name]]))
            if sim > 0.95:
                issues.append({
                    "severity": "error",
                    "type": "duplicate_node",
                    "parent": n_name,
                    "child": c_name,
                    "cosine": round(sim, 3),
                    "fix": f"Merge — '{n_name}' and '{c_name}' are essentially the same concept.",
                })

        for c in kids:
            c_name = names[c]
            sim = float(np.dot(emb[name_to_idx[n_name]], emb[name_to_idx[c_name]]))
            if sim < weak_threshold:
                issues.append({
                    "severity": "error",
                    "type": "weak_edge",
                    "parent": n_name,
                    "child": c_name,
                    "cosine": round(sim, 3),
                    "fix": f"Cosine similarity {sim:.2f} < {weak_threshold}. '{c_name}' may not be a subtype of '{n_name}'.",
                })

        if len(kids) >= 3:
            kid_embs = np.array([emb[name_to_idx[names[c]]] for c in kids])
            sims = []
            for i in range(len(kids)):
                for j in range(i + 1, len(kids)):
                    sims.append(float(np.dot(kid_embs[i], kid_embs[j])))
            if sims and np.mean(sims) < 0.20:
                issues.append({
                    "severity": "warn",
                    "type": "mixed_domain_siblings",
                    "parent": n_name,
                    "n_children": len(kids),
                    "mean_cosine": round(float(np.mean(sims)), 3),
                    "fix": f"Children of '{n_name}' are semantically diverse. Consider re-grouping into sub-domains.",
                })

    seen = set()
    out = []
    for it in issues:
        key = (it.get("type"), it.get("parent"), it.get("child"), it.get("node"))
        if key not in seen:
            seen.add(key)
            out.append(it)

    by_severity = {"error": 0, "warn": 0, "info": 0}
    by_type = {}
    for it in out:
        by_severity[it["severity"]] = by_severity.get(it["severity"], 0) + 1
        by_type[it["type"]] = by_type.get(it["type"], 0) + 1

    return {
        "summary": {
            "total_issues": len(out),
            "by_severity": by_severity,
            "by_type": by_type,
        },
        "issues": out,
    }


def main():
    args = sys.argv[1:]
    json_out = "--json" in args
    threshold = 0.30
    if "--threshold" in args:
        i = args.index("--threshold")
        threshold = float(args[i + 1])
    paths = [a for a in args if not a.startswith("--") and not a.replace(".", "").isdigit()]
    tax_path = paths[0] if paths else "taxonomy.json"
    if not os.path.exists(tax_path):
        print(f"ERROR: {tax_path} not found", file=sys.stderr)
        sys.exit(1)

    G = _taxonomy_to_graph(load_taxonomy(tax_path))
    report = lint_taxonomy(G, weak_threshold=threshold)

    if json_out:
        print(json.dumps(report, indent=2))
        return

    print(f"\nLinting {tax_path} ...")
    s = report["summary"]
    print(f"  Total issues: {s['total_issues']}")
    print(f"  By severity: ", ", ".join(f"{k}={v}" for k, v in s["by_severity"].items()))
    print(f"  By type:")
    for t, c in sorted(s["by_type"].items(), key=lambda x: -x[1]):
        print(f"    {t:<28} {c}")

    print(f"\nTop issues:")
    sev_order = {"error": 0, "warn": 1, "info": 2}
    for it in sorted(report["issues"], key=lambda x: sev_order[x["severity"]])[:20]:
        node = it.get("node") or it.get("parent")
        ch = it.get("child", "")
        print(f"  [{it['severity']:<5}] {it['type']:<26} {node} → {ch}")
        print(f"           ↳ {it['fix']}")


if __name__ == "__main__":
    main()
