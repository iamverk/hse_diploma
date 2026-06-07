#!/usr/bin/env python3
"""
Generate a unified taxonomy review report.

The report is meant for thesis/productization review: it combines taxonomy
structure, reference-free metrics, judge ratings, product assignment quality,
agent-judge readiness, and Akeneo export status into one artifact.

Usage:
    python tools/reporting.py --taxonomy taxonomy.json
    python tools/reporting.py \
        --taxonomy /path/to/taxonomy_final.json \
        --metrics-text /path/to/metrics_v2_final.txt \
        --rlpc-json /path/to/rlpc.json \
        --judge-ratings /path/to/judge_ratings.json
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
from pathlib import Path
from typing import Any

from tools.agent_judge import build_agent_judge_report
from tools.taxonomy_core import load_taxonomy


DEFAULT_ARTIFACT_DIR = Path("artifacts/local")
REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = Path(os.environ.get("BLIND_TAXONOMY_WORKSPACE", str(REPO_ROOT.parent)))
DEFAULT_HIDDEN_EXP10 = Path(
    os.environ.get(
        "BLIND_TAXONOMY_EXP10_DIR",
        str(WORKSPACE_ROOT / ".hidden_eval" / "exp10_results"),
    )
)


def _display_path(path: str | Path | None) -> str:
    if not path:
        return ""
    raw = str(path)
    p = Path(raw)
    try:
        return str(p.resolve().relative_to(REPO_ROOT.resolve()))
    except (OSError, ValueError):
        pass
    parts = p.parts
    if ".hidden_eval" in parts:
        idx = parts.index(".hidden_eval")
        return str(Path(".hidden_eval", *parts[idx + 1:]))
    return raw if not p.is_absolute() else p.name


def _load_json(path: str | Path | None, default: Any = None) -> Any:
    if not path:
        return default
    p = Path(path)
    if not p.exists():
        return default
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(data: Any, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return out


def _taxonomy_stats(taxonomy: dict) -> dict:
    depths: list[int] = []
    leaves = 0
    internal = 0
    child_counts = []
    top_level = []

    def leaf_count(node: dict) -> int:
        children = node.get("children") or []
        if not children:
            return 1
        return sum(leaf_count(child) for child in children)

    def walk(node: dict, depth: int) -> None:
        nonlocal leaves, internal
        depths.append(depth)
        children = node.get("children") or []
        if children:
            internal += 1
            child_counts.append(len(children))
        else:
            leaves += 1
        for child in children:
            walk(child, depth + 1)

    walk(taxonomy, 0)
    for child in taxonomy.get("children") or []:
        top_level.append({
            "id": str(child.get("id", "")),
            "name": str(child.get("name") or child.get("id") or ""),
            "leaf_count": leaf_count(child),
            "child_count": len(child.get("children") or []),
        })

    return {
        "nodes": len(depths),
        "edges": max(0, len(depths) - 1),
        "leaves": leaves,
        "internal_nodes": internal,
        "max_depth_levels": (max(depths) + 1) if depths else 0,
        "top_level_categories": len(taxonomy.get("children") or []),
        "mean_branching": round(sum(child_counts) / len(child_counts), 3) if child_counts else 0.0,
        "top_level_distribution": sorted(top_level, key=lambda row: (-row["leaf_count"], row["name"])),
    }


def parse_metrics_text(path: str | Path | None) -> dict:
    if not path or not Path(path).exists():
        return {}
    text = Path(path).read_text(encoding="utf-8")

    def grab(pattern: str, cast=float, default=None):
        match = re.search(pattern, text)
        if not match:
            return default
        return cast(match.group(1))

    return {
        "node_count": grab(r"Nodes:\s+(\d+)", int),
        "edge_count": grab(r"Edges:\s+(\d+)", int),
        "leaf_count": grab(r"Leaves:\s+(\d+)", int),
        "max_depth_edges": grab(r"Max depth:\s+(\d+)", int),
        "ces_mean": grab(r"Mean:\s+([0-9.]+)"),
        "ces_min": grab(r"Min:\s+([0-9.]+)"),
        "weak_edges_count": grab(r"Weak edges .*:\s+(\d+)", int),
        "csc_score": grab(r"Score:\s+([0-9.]+)"),
        "csc_p_value": grab(r"p-value:\s+([0-9.]+)"),
        "csc_pairs": grab(r"Pairs:\s+(\d+)", int),
        "chain_count": grab(r"Chains:\s+(\d+)", int),
        "branching_mean": grab(r"Branching:\s+mean=([0-9.]+)"),
        "branching_cv": grab(r"CV=([0-9.]+)"),
        "leaf_ratio": grab(r"Leaf ratio:\s+([0-9.]+)"),
        "rftq_d": grab(r"RFTQ-D SCORE:\s+([0-9.]+)"),
    }


def summarize_judge_ratings(path: str | Path | None) -> dict:
    data = _load_json(path, default={}) or {}
    summary = data.get("summary") or {}
    ratings = data.get("ratings") or []
    if not summary and ratings:
        values = [int(row["rating"]) for row in ratings if "rating" in row]
        if values:
            summary = {
                "n": len(values),
                "mean": sum(values) / len(values),
                "pct_valid_ge4": sum(1 for value in values if value >= 4) / len(values),
                "pct_invalid_le2": sum(1 for value in values if value <= 2) / len(values),
            }
    return {
        "model": data.get("model"),
        "date": data.get("date"),
        "summary": summary,
        "noted_issues": [row for row in ratings if row.get("note")][:10],
    }


def summarize_assignments(path: str | Path | None, limit: int = 5) -> dict:
    if not path or not Path(path).exists():
        return {"confident_examples": [], "review_examples": []}
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                row["_score"] = float(row.get("score") or 0)
            except ValueError:
                row["_score"] = 0.0
            rows.append(row)
    confident = [row for row in rows if str(row.get("needs_review", "")).lower() == "false"]
    review = [row for row in rows if str(row.get("needs_review", "")).lower() == "true"]
    confident.sort(key=lambda row: -row["_score"])
    review.sort(key=lambda row: row["_score"])
    return {
        "total_rows": len(rows),
        "confident_examples": confident[:limit],
        "review_examples": review[:limit],
    }


def export_status(artifact_dir: str | Path) -> dict:
    base = Path(artifact_dir)
    files = {
        "csv": base / "akeneo_categories.csv",
        "xlsx": base / "akeneo_categories.xlsx",
        "json": base / "akeneo_rest_payload.json",
    }
    status = {}
    for kind, path in files.items():
        entry = {
            "path": str(path),
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else 0,
        }
        if kind == "csv" and path.exists():
            with open(path, "r", encoding="utf-8") as f:
                entry["category_rows"] = max(0, sum(1 for _ in f) - 1)
        if kind == "json" and path.exists():
            payload = _load_json(path, default=[])
            entry["category_rows"] = len(payload) if isinstance(payload, list) else None
        status[kind] = entry
    return status


def build_lint_report(metrics: dict, agent_judge: dict) -> dict:
    weak_edges = int(metrics.get("weak_edges_count") or 0)
    redundant = agent_judge.get("redundant_edge_examples") or []
    low_info = agent_judge.get("low_information_leaf_examples") or []
    issues = []
    for row in redundant[:20]:
        issues.append({
            "severity": "warn",
            "type": "redundant_prefix",
            "parent": row.get("parent"),
            "child": row.get("child"),
        })
    for row in low_info[:20]:
        issues.append({
            "severity": "info",
            "type": "low_information_leaf",
            "path": row.get("path"),
            "label": row.get("label"),
        })
    by_severity = {"error": weak_edges, "warn": 0, "info": 0}
    by_type = {}
    for issue in issues:
        by_severity[issue["severity"]] += 1
        by_type[issue["type"]] = by_type.get(issue["type"], 0) + 1
    if weak_edges:
        by_type["weak_edge"] = weak_edges
    return {
        "summary": {
            "total_issues": weak_edges + len(issues),
            "by_severity": by_severity,
            "by_type": by_type,
            "source": "metrics_v2 weak-edge count plus deterministic agent-judge flags",
        },
        "issues": issues,
    }


def build_report_data(args: argparse.Namespace) -> dict:
    taxonomy = load_taxonomy(args.taxonomy)
    stats = _taxonomy_stats(taxonomy)
    metrics = parse_metrics_text(args.metrics_text)
    rlpc = _load_json(args.rlpc_json, default={}) or {}
    judge = summarize_judge_ratings(args.judge_ratings)
    assignment_metrics = _load_json(args.assignment_metrics, default={}) or {}
    agent_judge = _load_json(args.agent_judge, default=None)
    if agent_judge is None:
        agent_judge = build_agent_judge_report(taxonomy, assignment_metrics, taxonomy_path=args.taxonomy)
    assignment_examples = summarize_assignments(args.assignments)
    exports = export_status(args.artifact_dir)
    lint_report = _load_json(args.lint_report, default=None)
    if lint_report is None:
        lint_report = build_lint_report(metrics, agent_judge)

    metrics_json = {
        **metrics,
        "rlpc_score": rlpc.get("rlpc_score"),
        "rlpc_mono": rlpc.get("mono_mean_score"),
        "rlpc_step": rlpc.get("step_mean"),
        "rlpc_path_nli": rlpc.get("path_nli_mean"),
        "judge_mean": (judge.get("summary") or {}).get("mean"),
        "judge_valid_rate": (judge.get("summary") or {}).get("pct_valid_ge4"),
    }
    metrics_json["struct_score"] = _struct_score(metrics_json)
    metrics_json["rftq_j"] = _rftq_j_from_metrics(metrics_json)

    return {
        "taxonomy_path": _display_path(args.taxonomy),
        "artifact_dir": str(args.artifact_dir),
        "taxonomy_stats": stats,
        "metrics": metrics_json,
        "judge": judge,
        "assignment_metrics": assignment_metrics,
        "assignment_examples": assignment_examples,
        "agent_judge": agent_judge,
        "lint_report": lint_report,
        "exports": exports,
    }


def _struct_score(metrics: dict) -> float | None:
    if metrics.get("chain_count") is None and metrics.get("branching_cv") is None:
        return None
    chain_penalty = min(float(metrics.get("chain_count") or 0) * 0.05, 0.3)
    cv_penalty = min(float(metrics.get("branching_cv") or 0) * 0.2, 0.3)
    return max(0.0, 1.0 - chain_penalty - cv_penalty)


def _rftq_j_from_metrics(metrics: dict) -> float | None:
    required = ["ces_mean", "csc_score", "rlpc_score", "judge_mean", "struct_score"]
    if any(metrics.get(key) is None for key in required):
        return None
    return (
        0.30 * max(float(metrics["ces_mean"]), 0.0)
        + 0.20 * max(float(metrics["csc_score"]), 0.0)
        + 0.25 * max(float(metrics["rlpc_score"]), 0.0)
        + 0.15 * max(float(metrics["judge_mean"]) / 5.0, 0.0)
        + 0.10 * max(float(metrics["struct_score"]), 0.0)
    )


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _pct(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value) * 100:.1f}%"


def _short(text: str, limit: int = 88) -> str:
    value = " ".join(str(text).split())
    return value if len(value) <= limit else value[: limit - 3] + "..."


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown_report(data: dict) -> str:
    stats = data["taxonomy_stats"]
    metrics = data["metrics"]
    assignment = data["assignment_metrics"]
    agent = data["agent_judge"]
    lint = data["lint_report"]
    exports = data["exports"]
    judge_summary = (data["judge"].get("summary") or {})

    error_count = lint["summary"]["by_severity"].get("error", 0)
    export_ready = all(entry["exists"] for entry in exports.values())
    verdict = agent.get("verdict", "n/a")

    lines = [
        "# Taxonomy Review Report",
        "",
        f"Taxonomy: `{data['taxonomy_path']}`",
        "",
        "## Executive Summary",
        "",
        "| Check | Result |",
        "|---|---:|",
        f"| Agent judge verdict | {verdict} |",
        f"| Agent judge score | {_fmt(agent.get('overall_score_1_5'), 2)} / 5.00 |",
        f"| Blocking lint errors | {error_count} |",
        f"| Product assignments needing review | {_pct(assignment.get('needs_review_rate'))} |",
        f"| Akeneo export files present | {'yes' if export_ready else 'no'} |",
        "",
        "Interpretation: the taxonomy is structurally clean enough for a controlled PIM pilot, "
        "but product placement should enter a review queue before unattended import.",
        "",
        "## Taxonomy Structure",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Nodes | {stats['nodes']} |",
        f"| Edges | {stats['edges']} |",
        f"| Leaves | {stats['leaves']} |",
        f"| Max depth | {stats['max_depth_levels']} levels |",
        f"| Top-level categories | {stats['top_level_categories']} |",
        f"| Mean branching | {_fmt(stats['mean_branching'])} |",
        "",
        "### Top-Level Leaf Distribution",
        "",
        "| Category | Leaves | Direct children |",
        "|---|---:|---:|",
    ]
    for row in stats["top_level_distribution"]:
        lines.append(f"| {row['name']} | {row['leaf_count']} | {row['child_count']} |")

    lines.extend([
        "",
        "## Reference-Free Metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| CES mean | {_fmt(metrics.get('ces_mean'), 4)} |",
        f"| CES minimum | {_fmt(metrics.get('ces_min'), 4)} |",
        f"| Weak edges | {metrics.get('weak_edges_count', 'n/a')} |",
        f"| CSC | {_fmt(metrics.get('csc_score'), 4)} |",
        f"| RLPC | {_fmt(metrics.get('rlpc_score'), 4)} |",
        f"| LLM judge mean | {_fmt(judge_summary.get('mean'), 2)} / 5.00 |",
        f"| LLM judge valid paths | {_pct(judge_summary.get('pct_valid_ge4'))} |",
        f"| RFTQ-J reconstructed | {_fmt(metrics.get('rftq_j'), 4)} |",
        "",
        "## Linter and Quality Flags",
        "",
        "| Severity | Count |",
        "|---|---:|",
    ])
    for severity, count in lint["summary"]["by_severity"].items():
        lines.append(f"| {severity} | {count} |")
    lines.extend([
        "",
        "Top deterministic flags:",
        "",
    ])
    if lint["issues"]:
        for issue in lint["issues"][:10]:
            label = issue.get("child") or issue.get("label") or issue.get("path") or ""
            parent = issue.get("parent")
            if parent:
                lines.append(f"- `{issue['type']}`: {parent} -> {label}")
            else:
                lines.append(f"- `{issue['type']}`: {label}")
    else:
        lines.append("- No deterministic flags.")

    lines.extend([
        "",
        "## Product-to-Leaf Assignment",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Products assigned | {assignment.get('product_count', 'n/a')} |",
        f"| Leaf coverage in sample | {_pct(assignment.get('leaf_coverage'))} |",
        f"| Product coverage above threshold | {_pct(assignment.get('coverage'))} |",
        f"| Mean assignment score | {_fmt(assignment.get('mean_assignment_score'), 4)} |",
        f"| Ambiguity rate | {_pct(assignment.get('ambiguity_rate'))} |",
        f"| Needs-review rate | {_pct(assignment.get('needs_review_rate'))} |",
        "",
        "### Confident Assignment Examples",
        "",
        "| Product | Assigned leaf | Score |",
        "|---|---|---:|",
    ])
    for row in data["assignment_examples"]["confident_examples"]:
        lines.append(
            f"| {_cell(_short(row.get('title', '')))} | {_cell(row.get('assigned_leaf_name', ''))} | "
            f"{_fmt(row.get('_score'), 3)} |"
        )

    lines.extend([
        "",
        "### Review Queue Examples",
        "",
        "| Product | Proposed leaf | Score | Reason |",
        "|---|---|---:|---|",
    ])
    for row in data["assignment_examples"]["review_examples"]:
        lines.append(
            f"| {_cell(_short(row.get('title', '')))} | {_cell(row.get('assigned_leaf_name', ''))} | "
            f"{_fmt(row.get('_score'), 3)} | {_cell(row.get('review_reason', ''))} |"
        )

    lines.extend([
        "",
        "## Agent Judge",
        "",
        "| Criterion | Score |",
        "|---|---:|",
    ])
    for criterion in agent.get("criteria", []):
        lines.append(f"| {criterion['name']} | {_fmt(criterion.get('score_1_5'), 2)} / 5.00 |")
    lines.extend([
        "",
        "## Akeneo Export Readiness",
        "",
        "| Artifact | Present | Rows/bytes |",
        "|---|---:|---:|",
    ])
    for kind, entry in exports.items():
        rows_or_bytes = entry.get("category_rows") if entry.get("category_rows") is not None else entry.get("size_bytes", 0)
        lines.append(f"| `{Path(entry['path']).name}` | {'yes' if entry['exists'] else 'no'} | {rows_or_bytes} |")

    lines.extend([
        "",
        "## Artifact Inventory",
        "",
        f"- `assignment_metrics.json`: product-placement summary",
        f"- `product_assignments.csv`: product-to-leaf assignments and review flags",
        f"- `agent_judge_exp10.json`: deterministic readiness judge output",
        f"- `akeneo_categories.csv`, `akeneo_categories.xlsx`, `akeneo_rest_payload.json`: export payloads",
        f"- `report.html`: browser-readable version of this report",
        "",
        "## Decision",
        "",
        "Proceed with a controlled pilot import after category-manager review of low-confidence "
        "assignments and flagged naming issues. Do not run unattended bulk product categorization yet.",
    ])
    return "\n".join(lines) + "\n"


def markdown_to_html(markdown: str, title: str = "Taxonomy Review Report") -> str:
    lines = markdown.splitlines()
    body = []
    in_ul = False
    in_table = False

    def close_blocks():
        nonlocal in_ul, in_table
        if in_ul:
            body.append("</ul>")
            in_ul = False
        if in_table:
            body.append("</tbody></table>")
            in_table = False

    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            close_blocks()
            i += 1
            continue
        if line.startswith("|") and i + 1 < len(lines) and lines[i + 1].startswith("|---"):
            close_blocks()
            headers = [cell.strip() for cell in line.strip("|").split("|")]
            body.append("<table><thead><tr>" + "".join(f"<th>{html.escape(h)}</th>" for h in headers) + "</tr></thead><tbody>")
            in_table = True
            i += 2
            continue
        if in_table and line.startswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            body.append("<tr>" + "".join(f"<td>{_inline_html(c)}</td>" for c in cells) + "</tr>")
            i += 1
            continue
        if line.startswith("#"):
            close_blocks()
            level = min(6, len(line) - len(line.lstrip("#")))
            text = line[level:].strip()
            body.append(f"<h{level}>{html.escape(text)}</h{level}>")
        elif line.startswith("- "):
            if not in_ul:
                close_blocks()
                body.append("<ul>")
                in_ul = True
            body.append(f"<li>{_inline_html(line[2:].strip())}</li>")
        else:
            close_blocks()
            body.append(f"<p>{_inline_html(line)}</p>")
        i += 1
    close_blocks()
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #111827; margin: 0; background: #f8fafc; }}
    main {{ max-width: 1080px; margin: 0 auto; padding: 42px 28px 64px; background: white; }}
    h1 {{ font-size: 34px; margin-top: 0; }}
    h2 {{ margin-top: 34px; border-bottom: 1px solid #e5e7eb; padding-bottom: 8px; }}
    h3 {{ margin-top: 24px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 14px 0 22px; font-size: 14px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px 10px; vertical-align: top; }}
    th {{ background: #f3f4f6; text-align: left; }}
    code {{ background: #f3f4f6; padding: 1px 4px; border-radius: 4px; }}
    p, li {{ line-height: 1.55; }}
  </style>
</head>
<body><main>
{chr(10).join(body)}
</main></body>
</html>
"""


def _inline_html(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a unified taxonomy review report")
    parser.add_argument("--taxonomy", default=str(DEFAULT_HIDDEN_EXP10 / "taxonomy_final.json"))
    parser.add_argument("--metrics-text", default=str(DEFAULT_HIDDEN_EXP10 / "metrics_v2_final.txt"))
    parser.add_argument("--rlpc-json", default=str(DEFAULT_HIDDEN_EXP10 / "rlpc.json"))
    parser.add_argument("--judge-ratings", default=str(DEFAULT_HIDDEN_EXP10 / "judge_ratings.json"))
    parser.add_argument("--assignment-metrics", default=str(DEFAULT_ARTIFACT_DIR / "assignment_metrics.json"))
    parser.add_argument("--assignments", default=str(DEFAULT_ARTIFACT_DIR / "product_assignments.csv"))
    parser.add_argument("--agent-judge", default=str(DEFAULT_ARTIFACT_DIR / "agent_judge_exp10.json"))
    parser.add_argument("--lint-report", default=None)
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--metrics-out", default=str(DEFAULT_ARTIFACT_DIR / "metrics.json"))
    parser.add_argument("--lint-out", default=str(DEFAULT_ARTIFACT_DIR / "lint_report.json"))
    parser.add_argument("--out", default=str(DEFAULT_ARTIFACT_DIR / "report.md"))
    parser.add_argument("--html-out", default=str(DEFAULT_ARTIFACT_DIR / "report.html"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data = build_report_data(args)
    out = Path(args.out)
    html_out = Path(args.html_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown_report(data), encoding="utf-8")
    html_out.write_text(markdown_to_html(out.read_text(encoding="utf-8")), encoding="utf-8")
    _write_json(data["metrics"], args.metrics_out)
    _write_json(data["lint_report"], args.lint_out)
    print(f"Wrote: {out}")
    print(f"Wrote: {html_out}")
    print(f"Wrote: {args.metrics_out}")
    print(f"Wrote: {args.lint_out}")


if __name__ == "__main__":
    main()
