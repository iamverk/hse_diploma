#!/bin/bash
# stop-snapshot.sh — stop hook
# Snapshots taxonomy.json and logs session end status.
#
# Input (stdin): { "status": "completed|aborted|error", "hook_event_name": "stop", "workspace_roots": [...] }
# Output (stdout): not used (informational hook)

set -euo pipefail

TAXONOMY_FILE="taxonomy.json"
HISTORY_DIR="output/taxonomy_history"
EVENTS_LOG="output/hook_events.jsonl"

main() {
    local json_input
    json_input=$(cat)

    local status
    status=$(echo "$json_input" | jq -r '.status // "unknown"' 2>/dev/null)

    local ts
    ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    local epoch
    epoch=$(date +%s)

    # Snapshot taxonomy
    mkdir -p "$HISTORY_DIR"
    if [[ -f "$TAXONOMY_FILE" ]]; then
        cp "$TAXONOMY_FILE" "$HISTORY_DIR/snapshot_${epoch}.json"
        echo "Hook: snapshot saved to $HISTORY_DIR/snapshot_${epoch}.json" >&2
    fi

    # Log event
    mkdir -p output
    echo "{\"event\":\"stop\",\"status\":\"$status\",\"ts\":\"$ts\"}" >> "$EVENTS_LOG" 2>/dev/null || true

    echo "Hook: session ended with status=$status" >&2

    # No meaningful stdout for stop hook
    echo '{}'
}

if ! command -v jq &> /dev/null; then
    echo '{}'
    exit 0
fi

main "$@"
