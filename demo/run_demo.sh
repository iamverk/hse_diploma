#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PYTHON_BIN="${PYTHON:-python}"
OUT_DIR="${OUT_DIR:-$ROOT_DIR/artifacts/demo}"
PRODUCTS="${PRODUCTS:-$ROOT_DIR/data/products.jsonl}"
PRODUCT_LIMIT="${PRODUCT_LIMIT:-150}"
BACKEND="${BACKEND:-auto}"
HIDDEN_EXP10="${BLIND_TAX_HIDDEN_EXP10:-}"

if [[ -z "${TAXONOMY:-}" ]]; then
  TAXONOMY="$ROOT_DIR/taxonomy.json"
fi

mkdir -p "$OUT_DIR"

echo "== blind-taxonomy demo =="
echo "Python:   $PYTHON_BIN"
echo "Taxonomy: $TAXONOMY"
echo "Products: $PRODUCTS"
echo "Limit:    $PRODUCT_LIMIT"
echo "Backend:  $BACKEND"
echo "Out:      $OUT_DIR"
echo

"$PYTHON_BIN" "$ROOT_DIR/tools/assignment.py" \
  "$PRODUCTS" "$TAXONOMY" \
  --out "$OUT_DIR/product_assignments.csv" \
  --metrics-out "$OUT_DIR/assignment_metrics.json" \
  --report-out "$OUT_DIR/assignment_report.md" \
  --limit "$PRODUCT_LIMIT" \
  --backend "$BACKEND"

echo
"$PYTHON_BIN" "$ROOT_DIR/tools/agent_judge.py" \
  "$TAXONOMY" \
  --assignment-metrics "$OUT_DIR/assignment_metrics.json" \
  --out "$OUT_DIR/agent_judge_exp10.json" \
  --report-out "$OUT_DIR/agent_judge_exp10.md"

echo
"$PYTHON_BIN" "$ROOT_DIR/tools/akeneo_export.py" \
  "$TAXONOMY" \
  --output "$OUT_DIR/akeneo_categories.csv"

"$PYTHON_BIN" "$ROOT_DIR/tools/akeneo_export.py" \
  "$TAXONOMY" \
  --xlsx \
  --output "$OUT_DIR/akeneo_categories.xlsx"

"$PYTHON_BIN" "$ROOT_DIR/tools/akeneo_export.py" \
  "$TAXONOMY" \
  --json \
  --output "$OUT_DIR/akeneo_rest_payload.json"

METRICS_TEXT="$OUT_DIR/missing_metrics_v2.txt"
RLPC_JSON="$OUT_DIR/missing_rlpc.json"
JUDGE_RATINGS="$OUT_DIR/missing_judge_ratings.json"

if [[ -n "$HIDDEN_EXP10" && "$TAXONOMY" == "$HIDDEN_EXP10/taxonomy_final.json" ]]; then
  [[ -f "$HIDDEN_EXP10/metrics_v2_final.txt" ]] && METRICS_TEXT="$HIDDEN_EXP10/metrics_v2_final.txt"
  [[ -f "$HIDDEN_EXP10/rlpc.json" ]] && RLPC_JSON="$HIDDEN_EXP10/rlpc.json"
  [[ -f "$HIDDEN_EXP10/judge_ratings.json" ]] && JUDGE_RATINGS="$HIDDEN_EXP10/judge_ratings.json"
fi

echo
"$PYTHON_BIN" "$ROOT_DIR/tools/reporting.py" \
  --taxonomy "$TAXONOMY" \
  --metrics-text "$METRICS_TEXT" \
  --rlpc-json "$RLPC_JSON" \
  --judge-ratings "$JUDGE_RATINGS" \
  --assignment-metrics "$OUT_DIR/assignment_metrics.json" \
  --assignments "$OUT_DIR/product_assignments.csv" \
  --agent-judge "$OUT_DIR/agent_judge_exp10.json" \
  --artifact-dir "$OUT_DIR" \
  --metrics-out "$OUT_DIR/metrics.json" \
  --lint-out "$OUT_DIR/lint_report.json" \
  --out "$OUT_DIR/report.md" \
  --html-out "$OUT_DIR/report.html"

echo
echo "Demo artifacts:"
echo "  $OUT_DIR/product_assignments.csv"
echo "  $OUT_DIR/assignment_metrics.json"
echo "  $OUT_DIR/agent_judge_exp10.json"
echo "  $OUT_DIR/akeneo_categories.csv"
echo "  $OUT_DIR/akeneo_categories.xlsx"
echo "  $OUT_DIR/akeneo_rest_payload.json"
echo "  $OUT_DIR/report.md"
echo "  $OUT_DIR/report.html"
