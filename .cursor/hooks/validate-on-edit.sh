#!/bin/bash
# validate-on-edit.sh — afterFileEdit hook
# Auto-runs validate.py when taxonomy.json is edited.
# Agent receives metrics immediately without running validate.py manually.
#
# Input (stdin): { "file_path": "...", "edits": [...], "hook_event_name": "afterFileEdit", "workspace_roots": [...] }
# Output (stdout): { "followup_message": "..." }

set -euo pipefail

PYTHON="/Users/iamverk/anaconda3/envs/taxonomy-as-code/bin/python"
METRICS_LOG="output/hook_metrics.jsonl"

log() { echo -e "$1" >&2; }

main() {
    local json_input
    json_input=$(cat)

    local file_path
    file_path=$(echo "$json_input" | jq -r '.file_path // empty' 2>/dev/null)

    # Only trigger on taxonomy.json edits
    if [[ "$file_path" != *"taxonomy.json"* ]]; then
        echo '{}'
        exit 0
    fi

    log "Hook: taxonomy.json edited, running auto-validation..."

    # Run validate.py and capture structured JSON output
    local validate_output
    validate_output=$($PYTHON tools/validate.py 2>/dev/null || echo '{"error": "validate.py failed"}')

    # Parse key metrics
    local nliv csc composite nodes passed
    nliv=$(echo "$validate_output" | jq -r '.nliv_mean // "N/A"' 2>/dev/null)
    csc=$(echo "$validate_output" | jq -r '.csc_score // "N/A"' 2>/dev/null)
    composite=$(echo "$validate_output" | jq -r '.composite_score // "N/A"' 2>/dev/null)
    nodes=$(echo "$validate_output" | jq -r '.node_count // "N/A"' 2>/dev/null)
    passed=$(echo "$validate_output" | jq -r '.passed // "N/A"' 2>/dev/null)
    local weak_count
    weak_count=$(echo "$validate_output" | jq -r '.weak_edges_count // 0' 2>/dev/null)

    # Append to metrics log
    mkdir -p output
    local ts
    ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    echo "{\"ts\":\"$ts\",\"nliv\":$nliv,\"csc\":$csc,\"composite\":$composite,\"nodes\":$nodes,\"passed\":$passed,\"weak_edges\":$weak_count}" >> "$METRICS_LOG" 2>/dev/null || true

    # Build followup message for agent
    local msg="Auto-validate: NLIV=$nliv CSC=$csc Composite=$composite nodes=$nodes passed=$passed"
    if [[ "$weak_count" != "0" ]]; then
        msg="$msg | WARNING: $weak_count weak edges"
    fi

    cat << EOF
{"followup_message": "$msg"}
EOF
}

if ! command -v jq &> /dev/null; then
    echo '{}'
    exit 0
fi

main "$@"
