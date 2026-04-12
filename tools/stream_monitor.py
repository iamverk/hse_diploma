#!/usr/bin/env python3
"""
stream_monitor.py — Post-processor for cursor-agent stream-json output.

Reads a stream-json output file (not stdin pipe) and extracts:
  - Tool call counts (Edit, Shell, Read, etc.)
  - Taxonomy edit detections → runs validate.py
  - Full taxonomy.json read warnings
  - Session summary → stream_events.jsonl

Usage:
  python3 tools/stream_monitor.py output/cursor_stream_iter1.jsonl

Called by ralph.sh AFTER cursor-agent finishes each iteration.
Watchdog is handled by ralph.sh directly (file mtime monitoring).
"""

import sys
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────
VALIDATE_SCRIPT = "tools/validate.py"
EVENTS_LOG = "output/stream_events.jsonl"
METRICS_LOG = "output/hook_metrics.jsonl"
PYTHON = os.environ.get("PYTHON", "/Users/iamverk/anaconda3/envs/taxonomy-as-code/bin/python")


def log_event(event_type: str, data: dict):
    """Append structured event to stream_events.jsonl."""
    entry = {"ts": datetime.now().isoformat(), "type": event_type, **data}
    try:
        os.makedirs(os.path.dirname(EVENTS_LOG), exist_ok=True)
        with open(EVENTS_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def run_validate():
    """Run validate.py and return metrics dict."""
    try:
        result = subprocess.run(
            [PYTHON, VALIDATE_SCRIPT, "--json"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return json.loads(result.stdout.strip())
    except Exception as e:
        log_event("validate_error", {"error": str(e)})
    return None


def log_metrics(metrics: dict):
    """Append metrics to hook_metrics.jsonl."""
    if not metrics:
        return
    entry = {
        "ts": datetime.now().isoformat(),
        "source": "stream_monitor",
        "nliv_mean": metrics.get("nliv_mean", "N/A"),
        "csc_score": metrics.get("csc_score", "N/A"),
        "composite": metrics.get("composite_score", "N/A"),
        "node_count": metrics.get("node_count", "N/A"),
        "passed": metrics.get("passed", False),
    }
    try:
        os.makedirs(os.path.dirname(METRICS_LOG), exist_ok=True)
        with open(METRICS_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def process_stream_file(filepath: str):
    """Process a cursor-agent stream-json output file."""
    tool_calls = 0
    file_edits = 0
    shell_calls = 0
    taxonomy_edited = False
    taxonomy_reads = 0
    lines_total = 0

    path = Path(filepath)
    if not path.exists() or path.stat().st_size == 0:
        log_event("process_empty", {"file": filepath})
        print(f"Stream file empty or missing: {filepath}")
        return {"tool_calls": 0, "taxonomy_edited": False}

    with open(filepath) as f:
        for line in f:
            lines_total += 1
            line = line.strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type", "")

            # Tool call detection — cursor-agent stream-json format:
            # {"type": "tool_call", "tool_call": {"editToolCall": {"args": {"path": "..."}}}}
            if event_type == "tool_call":
                tool_calls += 1
                tc = event.get("tool_call", {})

                # Extract path from any tool call type
                file_path = ""
                tool_kind = ""
                for key in tc:
                    if key.endswith("ToolCall"):
                        tool_kind = key.replace("ToolCall", "")
                        args = tc[key].get("args", {})
                        file_path = args.get("path", args.get("file_path", ""))
                        break

                # Detect taxonomy.json edits
                if tool_kind in ("edit", "write"):
                    if "taxonomy.json" in str(file_path):
                        taxonomy_edited = True
                        file_edits += 1

                # Detect shell calls
                if tool_kind == "shell":
                    shell_calls += 1

                # Detect taxonomy reads
                if tool_kind == "read":
                    if "taxonomy.json" in str(file_path):
                        taxonomy_reads += 1

    summary = {
        "file": filepath,
        "lines": lines_total,
        "tool_calls": tool_calls,
        "file_edits": file_edits,
        "shell_calls": shell_calls,
        "taxonomy_edited": taxonomy_edited,
        "taxonomy_reads": taxonomy_reads,
    }

    log_event("stream_processed", summary)

    # If taxonomy was edited, validate
    if taxonomy_edited:
        metrics = run_validate()
        if metrics:
            log_metrics(metrics)
            summary["metrics"] = metrics

    print(json.dumps(summary))
    return summary


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: stream_monitor.py <stream-json-file>")
        sys.exit(1)

    process_stream_file(sys.argv[1])
