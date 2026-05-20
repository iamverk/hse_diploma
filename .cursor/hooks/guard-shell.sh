#!/bin/bash
# guard-shell.sh — beforeShellExecution hook
# Blocks dangerous commands that could corrupt experiment state.
#
# Input (stdin): { "command": "...", "cwd": "...", "hook_event_name": "beforeShellExecution", "workspace_roots": [...] }
# Output (stdout): { "permission": "allow|deny", "agentMessage": "..." }

set -euo pipefail

log() { echo -e "$1" >&2; }

return_allow() {
    cat << 'EOF'
{"permission": "allow"}
EOF
}

return_deny() {
    local msg="$1"
    cat << EOF
{"permission": "deny", "agentMessage": "$msg"}
EOF
}

main() {
    local json_input
    json_input=$(cat)

    if [[ -z "$json_input" ]]; then
        return_allow
        exit 0
    fi

    local command
    command=$(echo "$json_input" | jq -r '.command // empty' 2>/dev/null)

    if [[ -z "$command" ]]; then
        return_allow
        exit 0
    fi

    # ── DENY: destructive git commands ──────────────────────────────────
    if [[ "$command" =~ git\ reset\ --hard ]]; then
        return_deny "BLOCKED: git reset --hard is managed by ralph.sh, not by the agent."
        exit 0
    fi

    if [[ "$command" =~ git\ checkout\ --\ taxonomy\.json ]]; then
        return_deny "BLOCKED: taxonomy.json rollback is managed by ralph.sh."
        exit 0
    fi

    if [[ "$command" =~ git\ checkout\ .*\.json ]]; then
        return_deny "BLOCKED: git checkout of JSON files is managed by ralph.sh."
        exit 0
    fi

    # ── DENY: deleting taxonomy ─────────────────────────────────────────
    if [[ "$command" =~ rm.*taxonomy\.json ]] || [[ "$command" =~ rm\ -rf ]]; then
        return_deny "BLOCKED: cannot delete taxonomy.json or use rm -rf."
        exit 0
    fi

    # ── DENY: accessing forbidden files ─────────────────────────────────
    if [[ "$command" =~ gold_standard ]] || [[ "$command" =~ reference/ ]] || [[ "$command" =~ \.hidden_eval ]]; then
        return_deny "BLOCKED: accessing reference/gold_standard/.hidden_eval is forbidden."
        exit 0
    fi

    # ── DENY: git history access (agent must not peek at past solutions) ─
    if [[ "$command" =~ git\ log ]] || [[ "$command" =~ git\ show ]] || [[ "$command" =~ git\ diff.*HEAD ]]; then
        return_deny "BLOCKED: git history access is forbidden during taxonomy construction."
        exit 0
    fi

    # ── ALLOW: everything else ──────────────────────────────────────────
    return_allow
}

if ! command -v jq &> /dev/null; then
    return_allow
    exit 0
fi

main "$@"
