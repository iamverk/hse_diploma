#!/bin/bash
# rollback-counter.sh — afterFileEdit hook
# Tracks consecutive rollbacks per domain.
# When a domain hits 3+ consecutive discards, writes to stuck_domains.txt
# so ralph.sh can auto-skip it.
#
# Input (stdin): { "file_path": "...", "edits": [...], "hook_event_name": "afterFileEdit", "workspace_roots": [...] }
# Output (stdout): { "followup_message": "..." } or {}

set -euo pipefail

ROLLBACK_FILE="output/rollback_counts.json"
STUCK_FILE="output/stuck_domains.txt"
METRICS_LOG="output/hook_metrics.jsonl"
THRESHOLD=3

log() { echo -e "$1" >&2; }

main() {
    local json_input
    json_input=$(cat)

    local file_path
    file_path=$(echo "$json_input" | jq -r '.file_path // empty' 2>/dev/null)

    # Only trigger on prd.json edits (story status changes)
    if [[ "$file_path" != *"prd.json"* ]]; then
        echo '{}'
        exit 0
    fi

    mkdir -p output

    # Read current story from prd.json
    local current_story
    current_story=$(jq -r '.userStories[] | select(.passes == false) | .title' prd.json 2>/dev/null | head -1)

    if [[ -z "$current_story" ]]; then
        echo '{}'
        exit 0
    fi

    # Extract domain name from story title (e.g., "Expand L3: Electronics" → "Electronics")
    local domain
    domain=$(echo "$current_story" | grep -oP '(?:Expand|Refine|Fix).*?:\s*\K\S+' 2>/dev/null || echo "$current_story")

    # Initialize rollback counts file if needed
    if [[ ! -f "$ROLLBACK_FILE" ]]; then
        echo '{}' > "$ROLLBACK_FILE"
    fi

    # Read last metrics entry to check if this was a discard
    local last_passed
    last_passed=$(tail -1 "$METRICS_LOG" 2>/dev/null | jq -r '.passed // true' 2>/dev/null || echo "true")

    if [[ "$last_passed" == "false" ]]; then
        # Increment rollback count for this domain
        local current_count
        current_count=$(jq -r ".[\"$domain\"] // 0" "$ROLLBACK_FILE" 2>/dev/null || echo "0")
        local new_count=$((current_count + 1))

        # Update counts file
        jq ".[\"$domain\"] = $new_count" "$ROLLBACK_FILE" > "${ROLLBACK_FILE}.tmp" && mv "${ROLLBACK_FILE}.tmp" "$ROLLBACK_FILE"

        log "Hook: domain '$domain' rollback count: $new_count / $THRESHOLD"

        if [[ $new_count -ge $THRESHOLD ]]; then
            # Mark domain as stuck
            echo "$domain" >> "$STUCK_FILE"
            # Deduplicate
            sort -u "$STUCK_FILE" -o "$STUCK_FILE"

            cat << EOF
{"followup_message": "WARNING: Domain '$domain' has $new_count consecutive rollbacks (threshold: $THRESHOLD). This domain is stuck — likely Wu-Palmer CSC bias. Domain added to stuck_domains.txt. Consider invoking skip-stuck-domain skill to move on."}
EOF
            exit 0
        fi
    else
        # Success — reset counter for this domain
        if [[ -f "$ROLLBACK_FILE" ]]; then
            jq ".[\"$domain\"] = 0" "$ROLLBACK_FILE" > "${ROLLBACK_FILE}.tmp" && mv "${ROLLBACK_FILE}.tmp" "$ROLLBACK_FILE" 2>/dev/null || true
        fi
    fi

    echo '{}'
}

if ! command -v jq &> /dev/null; then
    echo '{}'
    exit 0
fi

main "$@"
