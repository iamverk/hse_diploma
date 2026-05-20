# Demo Runner

This directory contains a reproducible practical demo for the thesis pipeline.
It turns a taxonomy and a product sample into reviewable assignment, readiness,
PIM export, and reporting artifacts.

## Run

```bash
make demo
```

or:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,pim]"
make demo
```

The script uses the public repository `taxonomy.json` by default. To run a
private experiment output instead, set `TAXONOMY=/path/to/taxonomy_final.json`
explicitly.

## Inputs

- `TAXONOMY`: taxonomy JSON path. Optional.
- `PRODUCTS`: product JSONL path. Defaults to `data/products.jsonl`.
- `PRODUCT_LIMIT`: number of products to assign. Defaults to `150`.
- `BACKEND`: assignment backend, one of `auto`, `sentence-transformer`, or
  `lexical`. Defaults to `auto`.
- `OUT_DIR`: output artifact directory. Defaults to `artifacts/demo`.

For a tiny smoke run:

```bash
PRODUCTS=demo/products_sample.jsonl PRODUCT_LIMIT=8 BACKEND=lexical bash demo/run_demo.sh
```

## Outputs

- `product_assignments.csv`: product-to-leaf mapping with top-3 alternatives.
- `assignment_metrics.json`: placement coverage, ambiguity, and review-rate metrics.
- `assignment_report.md`: focused assignment review.
- `agent_judge_exp10.json` and `.md`: deterministic production-readiness review.
- `codex_judge_ratings.json`: second model-style path audit by Codex.
- `two_model_judge_protocol.md`: Claude Opus 4.7 vs Codex judge comparison.
- `akeneo_categories.csv`, `.xlsx`, `akeneo_rest_payload.json`: PIM import/export payloads.
- `report.md` and `report.html`: unified demo review report.
- `defense_demo_script.md`: one-page talk track for showing the demo during defense.
