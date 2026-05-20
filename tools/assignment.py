#!/usr/bin/env python3
"""
Assign products to leaf categories in a taxonomy.

The module is intentionally self-contained and works offline. By default it
tries to use a locally cached sentence-transformer model; if that is not
available, it falls back to a deterministic lexical hashing encoder. The
fallback is useful for demos and CI, while the sentence-transformer backend is
the intended production-candidate mode.

Usage:
    python tools/assignment.py data/products.jsonl taxonomy.json
    python tools/assignment.py data/products.jsonl taxonomy.json --out artifacts/demo/product_assignments.csv
    python tools/assignment.py data/products.jsonl taxonomy.json --backend lexical --limit 100
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from taxonomy_core import load_taxonomy


DEFAULT_THRESHOLD = 0.35
DEFAULT_AMBIGUITY_MARGIN = 0.05
DEFAULT_TOP_K = 3

_TAG_RE = re.compile(r"<[^>]+>")
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_SPACE_RE = re.compile(r"\s+")

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
    "into", "is", "it", "of", "on", "or", "the", "to", "with", "your",
    "our", "this", "that", "these", "those", "new", "set", "pack",
}


@dataclass(frozen=True)
class Leaf:
    id: str
    name: str
    description: str
    path_ids: tuple[str, ...]
    path_names: tuple[str, ...]

    @property
    def path(self) -> str:
        return " > ".join(self.path_names)

    @property
    def top_level_id(self) -> str:
        return self.path_ids[1] if len(self.path_ids) > 1 else self.id

    @property
    def top_level_name(self) -> str:
        return self.path_names[1] if len(self.path_names) > 1 else self.name

    @property
    def assignment_text(self) -> str:
        path = " > ".join(self.path_names[1:]) if len(self.path_names) > 1 else self.name
        return normalize_text(f"{self.name}. {self.description}. Path: {path}")


def normalize_text(value: object) -> str:
    """Convert a noisy product/category field to compact plain text."""
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = _TAG_RE.sub(" ", text)
    text = text.replace("\u00a0", " ")
    text = _SPACE_RE.sub(" ", text)
    return text.strip()


def tokenize(text: str) -> list[str]:
    tokens = _TOKEN_RE.findall(text.lower())
    return [t for t in tokens if len(t) > 1 and t not in _STOPWORDS]


def read_products(path: str | Path, limit: int | None = None) -> list[dict]:
    """Read JSONL products and normalize common title/name field variants."""
    products: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if limit is not None and len(products) >= limit:
                break
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc

            title = normalize_text(
                item.get("title")
                or item.get("name")
                or item.get("product_title")
                or item.get("query")
            )
            description = normalize_text(item.get("description") or item.get("product_description"))
            product_id = str(
                item.get("product_id")
                or item.get("id")
                or item.get("asin")
                or f"row-{line_no}"
            )
            products.append({
                **item,
                "product_id": product_id,
                "title": title,
                "description": description,
                "assignment_text": normalize_text(f"{title}. {description}"),
            })
    return products


def collect_leaves(taxonomy: dict) -> list[Leaf]:
    """Collect leaf nodes from a nested taxonomy JSON."""
    leaves: list[Leaf] = []

    def walk(node: dict, path_ids: tuple[str, ...], path_names: tuple[str, ...]) -> None:
        node_id = str(node["id"])
        name = str(node.get("name") or node_id)
        next_ids = (*path_ids, node_id)
        next_names = (*path_names, name)
        children = node.get("children") or []
        if not children:
            leaves.append(Leaf(
                id=node_id,
                name=name,
                description=normalize_text(node.get("description", "")),
                path_ids=next_ids,
                path_names=next_names,
            ))
            return
        for child in children:
            walk(child, next_ids, next_names)

    walk(taxonomy, (), ())
    return leaves


def _stable_bucket(token: str, dim: int) -> int:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "little") % dim


def _lexical_hash_encode(texts: Iterable[str], dim: int = 2048) -> np.ndarray:
    """Small deterministic bag-of-words encoder for offline demos and tests."""
    rows = []
    for text in texts:
        vec = np.zeros(dim, dtype=np.float32)
        tokens = tokenize(text)
        features = list(tokens)
        features.extend(f"{a}_{b}" for a, b in zip(tokens, tokens[1:]))
        for feat in features:
            vec[_stable_bucket(feat, dim)] += 1.0
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        rows.append(vec)
    return np.vstack(rows) if rows else np.zeros((0, dim), dtype=np.float32)


def encode_texts(
    texts: list[str],
    backend: str = "auto",
    model_name: str = "all-MiniLM-L6-v2",
    hash_dim: int = 2048,
) -> tuple[np.ndarray, str]:
    """Encode texts and return (matrix, backend_used)."""
    if backend not in {"auto", "sentence-transformer", "lexical"}:
        raise ValueError(f"Unknown backend: {backend}")

    if backend == "lexical":
        return _lexical_hash_encode(texts, dim=hash_dim), "lexical"

    if backend == "auto":
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(model_name, local_files_only=True)
            return np.asarray(model.encode(texts, normalize_embeddings=True)), f"sentence-transformer:{model_name}"
        except Exception as exc:
            print(
                f"INFO: local sentence-transformer unavailable ({exc}); using lexical fallback.",
                file=sys.stderr,
            )
            return _lexical_hash_encode(texts, dim=hash_dim), "lexical"

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_name)
    return np.asarray(model.encode(texts, normalize_embeddings=True)), f"sentence-transformer:{model_name}"


def assign_products(
    products: list[dict],
    leaves: list[Leaf],
    threshold: float = DEFAULT_THRESHOLD,
    ambiguity_margin: float = DEFAULT_AMBIGUITY_MARGIN,
    top_k: int = DEFAULT_TOP_K,
    backend: str = "auto",
    model_name: str = "all-MiniLM-L6-v2",
    hash_dim: int = 2048,
) -> tuple[list[dict], dict]:
    if not leaves:
        raise ValueError("Taxonomy has no leaf nodes")
    if not products:
        raise ValueError("No products to assign")

    k = max(1, min(top_k, len(leaves)))
    product_texts = [p["assignment_text"] for p in products]
    leaf_texts = [leaf.assignment_text for leaf in leaves]
    all_embeddings, backend_used = encode_texts(
        product_texts + leaf_texts,
        backend=backend,
        model_name=model_name,
        hash_dim=hash_dim,
    )
    product_embeddings = all_embeddings[:len(product_texts)]
    leaf_embeddings = all_embeddings[len(product_texts):]

    sims = product_embeddings @ leaf_embeddings.T
    rows: list[dict] = []
    scores: list[float] = []
    low_confidence = 0
    ambiguous = 0
    needs_review = 0
    assigned_leaf_ids: set[str] = set()

    for product_idx, product in enumerate(products):
        ranked = np.argsort(-sims[product_idx])[:k]
        top_scores = [float(sims[product_idx, i]) for i in ranked]
        top_leaves = [leaves[int(i)] for i in ranked]
        best = top_leaves[0]
        best_score = top_scores[0]
        second_score = top_scores[1] if len(top_scores) > 1 else -1.0
        is_low_confidence = best_score < threshold
        is_ambiguous = len(top_scores) > 1 and (best_score - second_score) < ambiguity_margin
        review = is_low_confidence or is_ambiguous

        scores.append(best_score)
        assigned_leaf_ids.add(best.id)
        low_confidence += int(is_low_confidence)
        ambiguous += int(is_ambiguous)
        needs_review += int(review)

        rows.append({
            "product_id": product["product_id"],
            "title": product["title"],
            "assigned_leaf_id": best.id,
            "assigned_leaf_name": best.name,
            "assigned_leaf_path": best.path,
            "top_level_id": best.top_level_id,
            "top_level_name": best.top_level_name,
            "score": round(best_score, 4),
            "top3_leaf_ids": "|".join(leaf.id for leaf in top_leaves),
            "top3_leaf_names": "|".join(leaf.name for leaf in top_leaves),
            "top3_scores": "|".join(f"{score:.4f}" for score in top_scores),
            "needs_review": str(review).lower(),
            "review_reason": _review_reason(is_low_confidence, is_ambiguous),
        })

    summary = {
        "product_count": len(products),
        "leaf_count": len(leaves),
        "assigned_leaf_count": len(assigned_leaf_ids),
        "leaf_coverage": round(len(assigned_leaf_ids) / len(leaves), 4),
        "threshold": threshold,
        "ambiguity_margin": ambiguity_margin,
        "coverage": round((len(products) - low_confidence) / len(products), 4),
        "mean_assignment_score": round(float(np.mean(scores)), 4),
        "min_assignment_score": round(float(np.min(scores)), 4),
        "max_assignment_score": round(float(np.max(scores)), 4),
        "low_confidence_count": low_confidence,
        "ambiguity_count": ambiguous,
        "ambiguity_rate": round(ambiguous / len(products), 4),
        "needs_review_count": needs_review,
        "needs_review_rate": round(needs_review / len(products), 4),
        "backend": backend_used,
    }
    return rows, summary


def _review_reason(low_confidence: bool, ambiguous: bool) -> str:
    reasons = []
    if low_confidence:
        reasons.append("low_confidence")
    if ambiguous:
        reasons.append("ambiguous_top2")
    return "|".join(reasons)


def write_assignments(rows: list[dict], path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "product_id",
        "title",
        "assigned_leaf_id",
        "assigned_leaf_name",
        "assigned_leaf_path",
        "top_level_id",
        "top_level_name",
        "score",
        "top3_leaf_ids",
        "top3_leaf_names",
        "top3_scores",
        "needs_review",
        "review_reason",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_metrics(summary: dict, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


def write_report(rows: list[dict], summary: dict, path: str | Path, sample_size: int = 10) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    sorted_rows = sorted(rows, key=lambda r: float(r["score"]))
    low_rows = sorted_rows[:sample_size]
    high_rows = list(reversed(sorted_rows[-sample_size:]))

    lines = [
        "# Product Assignment Review Report",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key in [
        "product_count",
        "leaf_count",
        "assigned_leaf_count",
        "leaf_coverage",
        "coverage",
        "mean_assignment_score",
        "ambiguity_rate",
        "needs_review_count",
        "needs_review_rate",
    ]:
        lines.append(f"| {key} | {summary[key]} |")
    lines.extend([
        f"| backend | {summary['backend']} |",
        "",
        "## Lowest-Confidence Assignments",
        "",
        "| Product | Assigned Leaf | Score | Review Reason |",
        "|---|---|---:|---|",
    ])
    for row in low_rows:
        lines.append(
            f"| {_md(row['title'])} | {_md(row['assigned_leaf_path'])} | "
            f"{row['score']} | {_md(row['review_reason'] or 'review_optional')} |"
        )
    lines.extend([
        "",
        "## Highest-Confidence Assignments",
        "",
        "| Product | Assigned Leaf | Score |",
        "|---|---|---:|",
    ])
    for row in high_rows:
        lines.append(
            f"| {_md(row['title'])} | {_md(row['assigned_leaf_path'])} | {row['score']} |"
        )
    lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _md(text: str, max_len: int = 120) -> str:
    text = normalize_text(text).replace("|", "\\|")
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "..."
    return text


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Assign products to leaf taxonomy categories")
    parser.add_argument("products", nargs="?", default="data/products.jsonl", help="Input products JSONL")
    parser.add_argument("taxonomy", nargs="?", default="taxonomy.json", help="Input taxonomy JSON")
    parser.add_argument("--out", default="artifacts/demo/product_assignments.csv", help="Output CSV path")
    parser.add_argument("--metrics-out", default="artifacts/demo/assignment_metrics.json", help="Output metrics JSON path")
    parser.add_argument("--report-out", default=None, help="Optional Markdown review report path")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="Low-confidence score threshold")
    parser.add_argument("--ambiguity-margin", type=float, default=DEFAULT_AMBIGUITY_MARGIN, help="Top-1/top-2 ambiguity margin")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Number of top leaves to keep")
    parser.add_argument("--limit", type=int, default=None, help="Optional product row limit for demos")
    parser.add_argument("--backend", choices=["auto", "sentence-transformer", "lexical"], default="auto")
    parser.add_argument("--model", default="all-MiniLM-L6-v2", help="Sentence-transformer model name")
    parser.add_argument("--hash-dim", type=int, default=2048, help="Lexical hashing dimension")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    products = read_products(args.products, limit=args.limit)
    leaves = collect_leaves(load_taxonomy(args.taxonomy))
    rows, summary = assign_products(
        products,
        leaves,
        threshold=args.threshold,
        ambiguity_margin=args.ambiguity_margin,
        top_k=args.top_k,
        backend=args.backend,
        model_name=args.model,
        hash_dim=args.hash_dim,
    )
    write_assignments(rows, args.out)
    write_metrics(summary, args.metrics_out)
    if args.report_out:
        write_report(rows, summary, args.report_out)

    print(f"Assigned {summary['product_count']} products to {summary['leaf_count']} leaves")
    print(f"Coverage @ {summary['threshold']}: {summary['coverage']:.1%}")
    print(f"Mean score: {summary['mean_assignment_score']:.4f}")
    print(f"Needs review: {summary['needs_review_count']} ({summary['needs_review_rate']:.1%})")
    print(f"Backend: {summary['backend']}")
    print(f"Wrote: {args.out}")
    print(f"Wrote: {args.metrics_out}")
    if args.report_out:
        print(f"Wrote: {args.report_out}")


if __name__ == "__main__":
    main()
