#!/usr/bin/env python3
"""
prepare_data.py — Parse Google Product Taxonomy and generate experiment datasets.

Usage:
    python tools/prepare_data.py --taxonomy-file ../../data/google_taxonomy/taxonomy-with-ids.en-US.txt
    python tools/prepare_data.py --taxonomy-file ../../data/google_taxonomy/taxonomy-with-ids.en-US.txt --output-dir data/experiments

Output structure:
    data/experiments/
        electronics/
            gold_standard.json   ← full Electronics taxonomy
            start_taxonomy.json  ← L1-L2 only (starting point)
            prd.json             ← task list for Ralph loop
        clothing/
            ...
        food/
            ...
        home/
            ...
"""

import argparse
import json
import re
from pathlib import Path
from collections import defaultdict


# ── Domain config ──────────────────────────────────────────────────────────────
DOMAINS = {
    "electronics": {
        "root_prefix": "Electronics",
        "root_id": "electronics",
        "root_name": "Electronics",
        "root_description": "Electronic devices, components, and related accessories",
    },
    "clothing": {
        "root_prefix": "Apparel & Accessories",
        "root_id": "apparel_accessories",
        "root_name": "Apparel & Accessories",
        "root_description": "Clothing, shoes, jewelry, and fashion accessories",
    },
    "food": {
        "root_prefix": "Food, Beverages & Tobacco",
        "root_id": "food_beverages_tobacco",
        "root_name": "Food, Beverages & Tobacco",
        "root_description": "Food products, drinks, tobacco, and related items",
    },
    "home": {
        "root_prefix": "Home & Garden",
        "root_id": "home_garden",
        "root_name": "Home & Garden",
        "root_description": "Home furnishings, garden supplies, and household items",
    },
}


# ── Parser ─────────────────────────────────────────────────────────────────────
def parse_taxonomy_file(filepath: str) -> list[dict]:
    """
    Parse Google Product Taxonomy txt file.

    Format:
        # Google_Product_Taxonomy_Version: ...
        1 - Animals & Pet Supplies
        3237 - Animals & Pet Supplies > Live Animals
        ...

    Returns list of {id, path, parts} dicts.
    """
    entries = []
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Split on " - " (first occurrence only)
            match = re.match(r"^(\d+)\s+-\s+(.+)$", line)
            if not match:
                continue
            gid = int(match.group(1))
            path_str = match.group(2).strip()
            parts = [p.strip() for p in path_str.split(">")]
            entries.append({"gid": gid, "path": path_str, "parts": parts})
    return entries


# ── Node ID generation ─────────────────────────────────────────────────────────
def name_to_id(name: str) -> str:
    """Convert category name to lowercase_snake_case id."""
    s = name.lower()
    s = re.sub(r"[&/\\]", "_and_", s)
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def make_unique_id(base_id: str, used: set) -> str:
    """Ensure id is unique by appending suffix if needed."""
    if base_id not in used:
        return base_id
    i = 2
    while f"{base_id}_{i}" in used:
        i += 1
    return f"{base_id}_{i}"


# ── Taxonomy builder ───────────────────────────────────────────────────────────
def build_taxonomy_json(entries: list[dict], domain_cfg: dict) -> dict:
    """
    Build nested taxonomy JSON from filtered entries.

    Returns taxonomy dict compatible with taxonomy_core.py:
    {
        "id": "root_id",
        "name": "Root Name",
        "description": "...",
        "children": [...]
    }
    """
    prefix = domain_cfg["root_prefix"]

    # Filter entries belonging to this domain (path starts with root_prefix)
    domain_entries = [
        e for e in entries
        if e["parts"][0] == prefix
    ]

    # Build nested dict: path_tuple → node_info
    # We'll use a tree structure: node = {name, description, children_dict}
    tree = {}  # path_tuple -> {"name": str, "children": dict}

    for entry in domain_entries:
        parts = entry["parts"]
        node = tree
        for depth, part in enumerate(parts):
            key = tuple(parts[: depth + 1])
            if key not in tree:
                tree[key] = {"name": part, "children": set()}
            if depth > 0:
                parent_key = tuple(parts[:depth])
                tree[parent_key]["children"].add(key)

    def _build_node(path_tuple: tuple, used_ids: set) -> dict:
        info = tree[path_tuple]
        name = info["name"]
        base_id = name_to_id(name)
        node_id = make_unique_id(base_id, used_ids)
        used_ids.add(node_id)

        description = f"Products and items in the {name} category"

        child_keys = sorted(info["children"])
        children = [_build_node(ck, used_ids) for ck in child_keys]

        node = {
            "id": node_id,
            "name": name,
            "description": description,
        }
        if children:
            node["children"] = children
        return node

    used_ids: set = set()

    # Build root node — override id/name/description from config
    root_key = (prefix,)
    if root_key not in tree:
        # No entries matched
        return {
            "id": domain_cfg["root_id"],
            "name": domain_cfg["root_name"],
            "description": domain_cfg["root_description"],
            "children": [],
        }

    root_node = _build_node(root_key, used_ids)
    root_node["id"] = domain_cfg["root_id"]
    root_node["name"] = domain_cfg["root_name"]
    root_node["description"] = domain_cfg["root_description"]

    return root_node


def make_start_taxonomy(full_taxonomy: dict, max_depth: int = 2) -> dict:
    """Extract only L1..max_depth nodes (starting point for Ralph loop)."""
    import copy

    def _trim(node: dict, current_depth: int) -> dict:
        n = {
            "id": node["id"],
            "name": node["name"],
            "description": node["description"],
        }
        if current_depth < max_depth and node.get("children"):
            n["children"] = [_trim(c, current_depth + 1) for c in node["children"]]
        return n

    return _trim(full_taxonomy, 1)


# ── PRD generator ──────────────────────────────────────────────────────────────
def make_prd(domain: str, full_taxonomy: dict) -> dict:
    """Generate prd.json task list for a domain."""
    domain_name = full_taxonomy["name"]

    def get_children(node: dict) -> list:
        return node.get("children", [])

    l1_children = get_children(full_taxonomy)
    l1_names = [c["name"] for c in l1_children]

    stories = []

    # Story 1: Verify L1 structure
    stories.append({
        "id": 1,
        "title": f"Verify and complete L1 categories under {domain_name}",
        "acceptanceCriteria": (
            f"{domain_name} has {len(l1_children)} direct children. "
            "validate.py passes with 0 errors."
        ),
        "passes": False,
    })

    # Stories 2+: Expand each L1 category to L2
    for i, l1 in enumerate(l1_children[:4], start=2):
        l2_children = get_children(l1)
        target = max(2, len(l2_children))
        stories.append({
            "id": i,
            "title": f"Expand '{l1['name']}' to L2 subcategories",
            "acceptanceCriteria": (
                f"'{l1['name']}' has at least {target} children. "
                "validate.py passes."
            ),
            "passes": False,
        })

    # Story: Add L3 leaf nodes
    stories.append({
        "id": len(stories) + 1,
        "title": f"Add L3 leaf categories across {domain_name} subcategories",
        "acceptanceCriteria": (
            "Major L2 nodes each have 2-5 leaf children. validate.py passes."
        ),
        "passes": False,
    })

    # Story: Lint cleanup
    stories.append({
        "id": len(stories) + 1,
        "title": "Run lint and fix all warnings (single-child nodes, missing descriptions)",
        "acceptanceCriteria": "tools/validate.py reports 0 errors and 0 warnings.",
        "passes": False,
    })

    # Story: Metrics target
    stories.append({
        "id": len(stories) + 1,
        "title": "Achieve edge F1 > 0.5 vs gold standard",
        "acceptanceCriteria": (
            "python tools/metrics.py reports edge_f1 >= 0.50"
        ),
        "passes": False,
    })

    return {
        "projectName": f"{domain_name} Taxonomy Construction",
        "domain": domain,
        "branchName": f"taxonomy-{domain}-v1",
        "userStories": stories,
    }


# ── Stats ──────────────────────────────────────────────────────────────────────
def count_nodes(node: dict) -> int:
    return 1 + sum(count_nodes(c) for c in node.get("children", []))


def max_depth_fn(node: dict, d: int = 1) -> int:
    children = node.get("children", [])
    if not children:
        return d
    return max(max_depth_fn(c, d + 1) for c in children)


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Prepare experiment datasets from Google Taxonomy")
    parser.add_argument(
        "--taxonomy-file",
        default="../../data/google_taxonomy/taxonomy-with-ids.en-US.txt",
        help="Path to Google taxonomy .txt file",
    )
    parser.add_argument(
        "--output-dir",
        default="data/experiments",
        help="Output directory for experiments",
    )
    parser.add_argument(
        "--domains",
        nargs="+",
        default=list(DOMAINS.keys()),
        choices=list(DOMAINS.keys()),
        help="Domains to process (default: all)",
    )
    parser.add_argument(
        "--start-depth",
        type=int,
        default=2,
        help="Max depth for start_taxonomy.json (default: 2 = L1+L2 only)",
    )
    args = parser.parse_args()

    taxonomy_path = Path(args.taxonomy_file)
    if not taxonomy_path.exists():
        print(f"ERROR: taxonomy file not found: {taxonomy_path}")
        raise SystemExit(1)

    print(f"Parsing: {taxonomy_path}")
    all_entries = parse_taxonomy_file(str(taxonomy_path))
    print(f"Total entries: {len(all_entries)}")

    output_root = Path(args.output_dir)

    for domain in args.domains:
        cfg = DOMAINS[domain]
        domain_dir = output_root / domain
        domain_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n── {domain.upper()} ──")

        # Build full gold standard taxonomy
        full = build_taxonomy_json(all_entries, cfg)
        total_nodes = count_nodes(full)
        depth = max_depth_fn(full)
        print(f"  gold_standard: {total_nodes} nodes, depth {depth}")

        gold_path = domain_dir / "gold_standard.json"
        gold_path.write_text(json.dumps(full, indent=2, ensure_ascii=False))
        print(f"  Saved: {gold_path}")

        # Build start taxonomy (L1-L2 only)
        start = make_start_taxonomy(full, max_depth=args.start_depth)
        start_nodes = count_nodes(start)
        print(f"  start_taxonomy: {start_nodes} nodes (L1-L{args.start_depth})")

        start_path = domain_dir / "start_taxonomy.json"
        start_path.write_text(json.dumps(start, indent=2, ensure_ascii=False))
        print(f"  Saved: {start_path}")

        # Build prd.json
        prd = make_prd(domain, full)
        prd_path = domain_dir / "prd.json"
        prd_path.write_text(json.dumps(prd, indent=2, ensure_ascii=False))
        print(f"  Saved: {prd_path} ({len(prd['userStories'])} stories)")

    print(f"\nDone. Experiments ready in: {output_root.resolve()}")


if __name__ == "__main__":
    main()
