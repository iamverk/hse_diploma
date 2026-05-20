#!/usr/bin/env python3
"""
budget-reader.py — beforeReadFile hook
Trims large files to save context window tokens.

- taxonomy.json (>5KB): returns summary + current domain subtree only
- experiment_history.md: returns last 2 experiments only

Input (stdin): { "file_path": "...", "content": "...", "hook_event_name": "beforeReadFile", "workspace_roots": [...] }
Output (stdout): { "permission": "allow", "content": "trimmed content" } or { "permission": "allow" }
"""

import json
import sys
import os

def get_current_domain():
    """Parse progress.txt to find current story's domain."""
    try:
        with open("progress.txt", "r") as f:
            text = f.read()
        # Look for "Story N status:" pattern
        for line in text.split("\n"):
            if "story" in line.lower() and "status" in line.lower():
                # Extract domain hint from line
                return line
    except FileNotFoundError:
        pass
    return None


def summarize_taxonomy(content):
    """Return compact summary instead of full taxonomy JSON."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None

    def count_nodes(node):
        c = 1
        for child in node.get("children", []):
            c += count_nodes(child)
        return c

    def get_l1_names(node):
        return [ch.get("name", ch.get("id", "?")) for ch in node.get("children", [])]

    def get_subtree_summary(node, depth=0, max_depth=2):
        """Compact tree representation."""
        indent = "  " * depth
        name = node.get("name", node.get("id", "?"))
        children = node.get("children", [])
        lines = [f"{indent}- {name} ({len(children)} children)"]
        if depth < max_depth:
            for ch in children:
                lines.extend(get_subtree_summary(ch, depth + 1, max_depth))
        elif children:
            child_names = [c.get("name", c.get("id", "?")) for c in children]
            lines.append(f"{indent}  [{', '.join(child_names)}]")
        return lines

    total = count_nodes(data)
    l1_names = get_l1_names(data)

    summary_lines = [
        f"# taxonomy.json summary (trimmed by budget-reader hook)",
        f"Total nodes: {total}",
        f"Root: {data.get('name', 'unknown')}",
        f"L1 domains ({len(l1_names)}): {', '.join(l1_names)}",
        "",
        "## Tree (depth 2):",
    ]
    summary_lines.extend(get_subtree_summary(data))
    summary_lines.append("")
    summary_lines.append("# To read full taxonomy, use: $PYTHON tools/taxonomy_cli.py tree")
    summary_lines.append("# To read a specific subtree: $PYTHON tools/taxonomy_cli.py tree --root <node_id>")

    return "\n".join(summary_lines)


def trim_experiment_history(content):
    """Return only last 2 experiments from experiment_history.md."""
    lines = content.split("\n")
    # Find experiment headers (## Experiment N)
    exp_starts = []
    for i, line in enumerate(lines):
        if line.startswith("## Exp") or line.startswith("## Experiment"):
            exp_starts.append(i)

    if len(exp_starts) <= 2:
        return None  # small enough, no trimming

    # Keep header (before first experiment) + last 2 experiments
    header = lines[:exp_starts[0]]
    last_two_start = exp_starts[-2]
    trimmed = header + [
        f"# (trimmed by budget-reader hook — showing last 2 of {len(exp_starts)} experiments)",
        ""
    ] + lines[last_two_start:]

    return "\n".join(trimmed)


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        print('{"permission": "allow"}')
        return

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print('{"permission": "allow"}')
        return

    file_path = data.get("file_path", "")
    content = data.get("content", "")

    # ── taxonomy.json: trim if > 5KB ─────────────────────────────────
    if "taxonomy.json" in file_path and len(content) > 5000:
        summary = summarize_taxonomy(content)
        if summary:
            result = {"permission": "allow", "content": summary}
            print(json.dumps(result))
            return

    # ── experiment_history.md: trim to last 2 experiments ────────────
    if "experiment_history" in file_path:
        trimmed = trim_experiment_history(content)
        if trimmed:
            result = {"permission": "allow", "content": trimmed}
            print(json.dumps(result))
            return

    # ── everything else: pass through ────────────────────────────────
    print('{"permission": "allow"}')


if __name__ == "__main__":
    main()
