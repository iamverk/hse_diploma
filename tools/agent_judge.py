#!/usr/bin/env python3
"""
Agent-style taxonomy judge.

This module provides a deterministic offline reviewer for a generated product
taxonomy. It is intentionally separate from the LLM-as-judge path scorer in
path_coherence.py: instead of asking a model to rate individual paths, it
reviews the whole taxonomy as a production artifact and emits an auditable
JSON/Markdown report.

Usage:
    python tools/agent_judge.py taxonomy.json
    python tools/agent_judge.py taxonomy.json --assignment-metrics artifacts/demo/assignment_metrics.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

import networkx as nx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from taxonomy_core import _taxonomy_to_graph, load_taxonomy


GENERIC_TERMS = {
    "accessories",
    "accessory",
    "equipment",
    "gear",
    "general",
    "goods",
    "items",
    "misc",
    "miscellaneous",
    "other",
    "products",
    "supplies",
    "supply",
    "things",
    "tools",
}


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())


def _name(node: dict) -> str:
    return str(node.get("name") or node.get("id") or "")


def _children(node: dict) -> list[dict]:
    return list(node.get("children") or [])


def _walk(node: dict, depth: int = 0, path: tuple[str, ...] = ()) -> Iterable[tuple[dict, int, tuple[str, ...]]]:
    current_path = (*path, _name(node))
    yield node, depth, current_path
    for child in _children(node):
        yield from _walk(child, depth + 1, current_path)


def _leaf_count(node: dict) -> int:
    children = _children(node)
    if not children:
        return 1
    return sum(_leaf_count(child) for child in children)


def _is_low_information_label(name: str, depth: int, is_leaf: bool) -> bool:
    tokens = set(_tokens(name))
    if not tokens:
        return True
    specific_tokens = tokens - GENERIC_TERMS
    if is_leaf and tokens & GENERIC_TERMS and len(specific_tokens) <= 1:
        return True
    if depth > 1 and not specific_tokens:
        return True
    return False


def _redundant_prefix(parent: str, child: str) -> bool:
    parent_tokens = set(_tokens(parent))
    child_tokens = _tokens(child)
    return bool(child_tokens and child_tokens[0] in parent_tokens and len(child_tokens) > 1)


def _coefficient_of_variation(values: list[int]) -> float:
    if not values:
        return 0.0
    mean = statistics.mean(values)
    if mean == 0:
        return 0.0
    return statistics.pstdev(values) / mean


def _clamp_score(value: float) -> float:
    return round(max(1.0, min(5.0, value)), 2)


def _load_assignment_metrics(path: str | Path | None) -> dict | None:
    if not path:
        return None
    metrics_path = Path(path)
    if not metrics_path.exists():
        return None
    with open(metrics_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _score_assignment(metrics: dict | None) -> tuple[float | None, list[str], list[str]]:
    if not metrics:
        return None, ["No product-to-leaf assignment metrics were provided."], [
            "Run tools/assignment.py on a product sample before treating the taxonomy as deployment-ready."
        ]

    coverage = float(metrics.get("coverage", 0.0))
    leaf_coverage = float(metrics.get("leaf_coverage", 0.0))
    review_rate = float(metrics.get("needs_review_rate", 1.0))
    mean_score = float(metrics.get("mean_assignment_score", 0.0))
    mean_norm = max(0.0, min(1.0, mean_score / 0.60))
    readiness_signal = (
        0.35 * coverage
        + 0.25 * leaf_coverage
        + 0.25 * (1.0 - review_rate)
        + 0.15 * mean_norm
    )
    score = _clamp_score(1.0 + 4.0 * readiness_signal)
    evidence = [
        f"product coverage above threshold: {coverage:.1%}",
        f"leaf coverage in sample: {leaf_coverage:.1%}",
        f"assignments needing review: {review_rate:.1%}",
        f"mean assignment score: {mean_score:.3f}",
    ]
    risks = []
    if review_rate > 0.50:
        risks.append("High review rate: product placement is not yet reliable enough for unattended import.")
    if leaf_coverage < 0.50:
        risks.append("Many leaves receive no sampled products; check whether categories are too narrow or absent from the sample.")
    if coverage < 0.60:
        risks.append("Less than 60% of sampled products exceed the confidence threshold.")
    return score, evidence, risks


def build_agent_judge_report(taxonomy: dict, assignment_metrics: dict | None = None, taxonomy_path: str = "") -> dict:
    G = _taxonomy_to_graph(taxonomy)
    rows = list(_walk(taxonomy))
    root_count = sum(1 for _, degree in G.in_degree() if degree == 0)
    is_dag = nx.is_directed_acyclic_graph(G)

    leaves = [(node, depth, path) for node, depth, path in rows if not _children(node)]
    internal = [(node, depth, path) for node, depth, path in rows if _children(node)]
    internal_nonroot = [(node, depth, path) for node, depth, path in internal if depth > 0]
    max_depth_levels = max((depth for _, depth, _ in rows), default=0) + 1
    top_level_nodes = _children(taxonomy)
    top_level_distribution = [
        {
            "id": str(node.get("id", "")),
            "name": _name(node),
            "leaf_count": _leaf_count(node),
            "child_count": len(_children(node)),
        }
        for node in top_level_nodes
    ]
    top_leaf_counts = [row["leaf_count"] for row in top_level_distribution]
    top_leaf_cv = _coefficient_of_variation(top_leaf_counts)

    child_counts = [len(_children(node)) for node, _, _ in internal]
    single_child_count = sum(1 for node, _, _ in internal_nonroot if len(_children(node)) == 1)
    single_child_ratio = single_child_count / max(1, len(internal_nonroot))

    normalized_names = [_normalize_name(_name(node)) for node, _, _ in rows]
    duplicate_names = {name: count for name, count in Counter(normalized_names).items() if name and count > 1}
    redundant_edges = []
    for parent, _, _ in internal:
        for child in _children(parent):
            if _redundant_prefix(_name(parent), _name(child)):
                redundant_edges.append({"parent": _name(parent), "child": _name(child)})

    generic_leaf_labels = [
        {"path": " > ".join(path), "label": _name(node)}
        for node, depth, path in leaves
        if _is_low_information_label(_name(node), depth, is_leaf=True)
    ]
    long_labels = [
        {"path": " > ".join(path), "label": _name(node)}
        for node, _, path in rows
        if len(_tokens(_name(node))) > 6
    ]

    structural_penalty = 0.0
    if not is_dag:
        structural_penalty += 2.0
    if root_count != 1:
        structural_penalty += 1.0
    if max_depth_levels < 3:
        structural_penalty += 0.6
    elif max_depth_levels > 5:
        structural_penalty += min(1.0, 0.35 * (max_depth_levels - 5))
    if len(top_level_nodes) < 5 or len(top_level_nodes) > 14:
        structural_penalty += 0.4
    structural_penalty += min(1.2, single_child_ratio * 3.0)
    if top_leaf_cv > 1.15:
        structural_penalty += min(0.8, (top_leaf_cv - 1.15) * 0.8)
    structural_score = _clamp_score(5.0 - structural_penalty)

    naming_penalty = 0.0
    naming_penalty += min(1.2, len(duplicate_names) * 0.3)
    naming_penalty += min(1.5, (len(generic_leaf_labels) / max(1, len(leaves))) * 3.0)
    naming_penalty += min(1.0, (len(redundant_edges) / max(1, G.number_of_edges())) * 2.0)
    naming_penalty += min(0.6, (len(long_labels) / max(1, len(rows))) * 2.0)
    naming_score = _clamp_score(5.0 - naming_penalty)

    governance_penalty = 0.0
    if not is_dag or root_count != 1:
        governance_penalty += 2.0
    governance_penalty += min(1.0, single_child_count / max(1, len(internal_nonroot)) * 2.0)
    governance_penalty += min(0.8, (len(generic_leaf_labels) + len(redundant_edges)) / max(1, len(rows)) * 2.5)
    if assignment_metrics and float(assignment_metrics.get("needs_review_rate", 0.0)) > 0.70:
        governance_penalty += 0.35
    governance_score = _clamp_score(5.0 - governance_penalty)

    assignment_score, assignment_evidence, assignment_risks = _score_assignment(assignment_metrics)

    criteria = [
        {
            "name": "Global structure and navigability",
            "weight": 0.30,
            "score_1_5": structural_score,
            "evidence": [
                f"{G.number_of_nodes()} nodes, {len(leaves)} leaves, {max_depth_levels} levels",
                f"{len(top_level_nodes)} top-level categories",
                f"single-child internal ratio: {single_child_ratio:.1%}",
                f"top-level leaf imbalance CV: {top_leaf_cv:.2f}",
            ],
            "risks": _structural_risks(max_depth_levels, len(top_level_nodes), single_child_ratio, top_leaf_cv),
        },
        {
            "name": "Naming specificity and category actionability",
            "weight": 0.25,
            "score_1_5": naming_score,
            "evidence": [
                f"{len(generic_leaf_labels)} low-information leaf labels",
                f"{len(redundant_edges)} redundant parent-child prefixes",
                f"{len(duplicate_names)} duplicate normalized labels",
                f"{len(long_labels)} labels longer than six tokens",
            ],
            "risks": _naming_risks(generic_leaf_labels, redundant_edges, duplicate_names, long_labels),
        },
        {
            "name": "Product placement readiness",
            "weight": 0.25,
            "score_1_5": assignment_score,
            "evidence": assignment_evidence,
            "risks": assignment_risks,
        },
        {
            "name": "Governance and audit readiness",
            "weight": 0.20,
            "score_1_5": governance_score,
            "evidence": [
                f"valid DAG: {is_dag}",
                f"root count: {root_count}",
                f"auditable top-level distribution is available",
                "agent judge is deterministic and reproducible",
            ],
            "risks": _governance_risks(is_dag, root_count, assignment_metrics),
        },
    ]

    active = [c for c in criteria if c["score_1_5"] is not None]
    weight_sum = sum(float(c["weight"]) for c in active) or 1.0
    overall = sum(float(c["score_1_5"]) * float(c["weight"]) for c in active) / weight_sum
    if assignment_score is not None and assignment_score < 3.0:
        overall = min(overall, 3.95)
    overall = round(overall, 2)

    return {
        "taxonomy_path": taxonomy_path,
        "overall_score_1_5": overall,
        "overall_normalized": round(overall / 5.0, 4),
        "verdict": _verdict(overall),
        "criteria": criteria,
        "statistics": {
            "nodes": G.number_of_nodes(),
            "edges": G.number_of_edges(),
            "leaves": len(leaves),
            "internal_nodes": len(internal),
            "max_depth_levels": max_depth_levels,
            "top_level_categories": len(top_level_nodes),
            "single_child_internal_nodes": single_child_count,
            "single_child_internal_ratio": round(single_child_ratio, 4),
            "top_level_leaf_cv": round(top_leaf_cv, 4),
        },
        "top_level_distribution": sorted(top_level_distribution, key=lambda row: (-row["leaf_count"], row["name"])),
        "flagged_paths": _flagged_paths(leaves)[:12],
        "low_information_leaf_examples": generic_leaf_labels[:12],
        "redundant_edge_examples": redundant_edges[:12],
        "duplicate_normalized_labels": duplicate_names,
    }


def _normalize_name(name: str) -> str:
    return " ".join(_tokens(name))


def _structural_risks(max_depth_levels: int, top_level_count: int, single_child_ratio: float, top_leaf_cv: float) -> list[str]:
    risks = []
    if max_depth_levels > 5:
        risks.append("The hierarchy is deep enough to slow navigation and business review.")
    if max_depth_levels < 3:
        risks.append("The hierarchy is too shallow for meaningful product discovery.")
    if top_level_count < 5 or top_level_count > 14:
        risks.append("The number of top-level categories is outside the expected e-commerce navigation band.")
    if single_child_ratio > 0.10:
        risks.append("Single-child chains suggest wrapper nodes or unnecessary hierarchy levels.")
    if top_leaf_cv > 1.15:
        risks.append("Leaf distribution is imbalanced across top-level domains.")
    return risks


def _naming_risks(generic_leaf_labels: list[dict], redundant_edges: list[dict], duplicate_names: dict, long_labels: list[dict]) -> list[str]:
    risks = []
    if generic_leaf_labels:
        risks.append("Some leaves are too generic to support confident product assignment.")
    if redundant_edges:
        risks.append("Some child labels repeat the parent concept instead of adding specificity.")
    if duplicate_names:
        risks.append("Duplicate normalized labels may create ambiguous category codes or UI labels.")
    if long_labels:
        risks.append("Very long labels may not fit PIM/category navigation interfaces.")
    return risks


def _governance_risks(is_dag: bool, root_count: int, assignment_metrics: dict | None) -> list[str]:
    risks = []
    if not is_dag:
        risks.append("The graph is not a DAG.")
    if root_count != 1:
        risks.append("The taxonomy does not have exactly one root.")
    if assignment_metrics and float(assignment_metrics.get("needs_review_rate", 0.0)) > 0.70:
        risks.append("A high product-placement review rate should be handled before unattended PIM import.")
    return risks


def _flagged_paths(leaves: list[tuple[dict, int, tuple[str, ...]]]) -> list[dict]:
    flagged = []
    for node, depth, path in leaves:
        reasons = []
        leaf_name = _name(node)
        if _is_low_information_label(leaf_name, depth, is_leaf=True):
            reasons.append("low_information_leaf")
        if len(path) > 5:
            reasons.append("deep_path")
        for parent, child in zip(path[:-1], path[1:]):
            if _redundant_prefix(parent, child):
                reasons.append("redundant_prefix")
                break
        if reasons:
            flagged.append({
                "path": " > ".join(path),
                "reasons": reasons,
                "risk_score": len(reasons),
            })
    flagged.sort(key=lambda row: (-row["risk_score"], row["path"]))
    return flagged


def _verdict(score: float) -> str:
    if score >= 4.2:
        return "ready for pilot import after ordinary business review"
    if score >= 3.5:
        return "pilot-ready with targeted review"
    if score >= 2.7:
        return "requires focused cleanup before pilot import"
    return "not ready for pilot import"


def write_json_report(report: dict, path: str | Path) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def write_markdown_report(report: dict, path: str | Path) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Agent Judge Report",
        "",
        f"Taxonomy: `{report.get('taxonomy_path') or 'taxonomy.json'}`",
        "",
        f"Overall score: **{report['overall_score_1_5']:.2f} / 5.00** "
        f"({report['overall_normalized']:.3f} normalized)",
        "",
        f"Verdict: **{report['verdict']}**",
        "",
        "## Criteria",
        "",
        "| Criterion | Weight | Score | Evidence | Main risks |",
        "|---|---:|---:|---|---|",
    ]
    for criterion in report["criteria"]:
        score = criterion["score_1_5"]
        score_text = "n/a" if score is None else f"{score:.2f}"
        evidence = "<br>".join(criterion["evidence"])
        risks = "<br>".join(criterion["risks"]) if criterion["risks"] else "No major risk detected."
        lines.append(
            f"| {criterion['name']} | {criterion['weight']:.2f} | {score_text} | {evidence} | {risks} |"
        )

    stats = report["statistics"]
    lines.extend([
        "",
        "## Structure Summary",
        "",
        f"- Nodes: {stats['nodes']}",
        f"- Leaves: {stats['leaves']}",
        f"- Max depth: {stats['max_depth_levels']} levels",
        f"- Top-level categories: {stats['top_level_categories']}",
        f"- Single-child internal nodes: {stats['single_child_internal_nodes']}",
        "",
        "## Top-Level Leaf Distribution",
        "",
        "| Top-level category | Leaves | Direct children |",
        "|---|---:|---:|",
    ])
    for row in report["top_level_distribution"]:
        lines.append(f"| {row['name']} | {row['leaf_count']} | {row['child_count']} |")

    lines.extend([
        "",
        "## Flagged Path Examples",
        "",
    ])
    if report["flagged_paths"]:
        for row in report["flagged_paths"][:10]:
            lines.append(f"- `{row['path']}`: {', '.join(row['reasons'])}")
    else:
        lines.append("No path-level heuristic flags.")

    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a deterministic agent-style taxonomy judge")
    parser.add_argument("taxonomy", nargs="?", default="taxonomy.json", help="Input taxonomy JSON")
    parser.add_argument(
        "--assignment-metrics",
        default=None,
        help="Optional assignment metrics JSON from tools/assignment.py",
    )
    parser.add_argument("--out", default="artifacts/demo/agent_judge_report.json", help="Output JSON report")
    parser.add_argument("--report-out", default="artifacts/demo/agent_judge_report.md", help="Output Markdown report")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    assignment_metrics_path = args.assignment_metrics
    if assignment_metrics_path is None:
        default_metrics = Path("artifacts/demo/assignment_metrics.json")
        assignment_metrics_path = str(default_metrics) if default_metrics.exists() else None

    taxonomy = load_taxonomy(args.taxonomy)
    assignment_metrics = _load_assignment_metrics(assignment_metrics_path)
    report = build_agent_judge_report(taxonomy, assignment_metrics, taxonomy_path=args.taxonomy)
    write_json_report(report, args.out)
    write_markdown_report(report, args.report_out)

    print(f"Agent judge score: {report['overall_score_1_5']:.2f}/5.00")
    print(f"Verdict: {report['verdict']}")
    print(f"Wrote: {args.out}")
    print(f"Wrote: {args.report_out}")


if __name__ == "__main__":
    main()
