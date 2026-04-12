#!/usr/bin/env python3
"""
stream_monitor.py — Real-time cursor-agent stream parser & watchdog.

Replaces broken Cursor hooks (beforeReadFile, stop, afterAgentResponse)
by parsing `--output-format stream-json` output from cursor-agent.

Features:
  1. WATCHDOG: kills cursor-agent if no output for SILENCE_TIMEOUT seconds
  2. AUTO-VALIDATE: runs validate.py when taxonomy.json edit detected in stream
  3. METRICS LOG: writes every tool call + metrics to output/stream_events.jsonl
  4. BUDGET GUARD: detects full taxonomy.json reads and logs warning

Usage:
  cursor-agent --output-format stream-json ... | python3 tools/stream_monitor.py --pid <PID>

Or via ralph.sh which pipes automatically.
"""

import sys
import json
import os
import time
import signal
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────
SILENCE_TIMEOUT = 300  # 5 minutes — kill agent if no output
VALIDATE_SCRIPT = "tools/validate.py"
EVENTS_LOG = "output/stream_events.jsonl"
METRICS_LOG = "output/hook_metrics.jsonl"
PYTHON = os.environ.get("PYTHON", "/Users/iamverk/anaconda3/envs/taxonomy-as-code/bin/python")

# ── State ──────────────────────────────────────────────────────────────
last_output_time = time.time()
agent_pid = None
taxonomy_edited = False
tool_calls = 0
file_edits = 0
shell_calls = 0
iteration_metrics = {}


def log_event(event_type: str, data: dict):
    """Append structured event to stream_events.jsonl."""
    entry = {
        "ts": datetime.now().isoformat(),
        "type": event_type,
        **data
    }
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
            capture_output=True, text=True, timeout=30,
            cwd=os.getcwd()
        )
        if result.returncode == 0:
            metrics = json.loads(result.stdout.strip())
            return metrics
    except Exception as e:
        log_event("validate_error", {"error": str(e)})
    return None


def log_metrics(metrics: dict):
    """Append metrics to hook_metrics.jsonl (same format as validate-on-edit hook)."""
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


def kill_agent(reason: str):
    """Kill the cursor-agent process."""
    global agent_pid
    if agent_pid:
        log_event("watchdog_kill", {"pid": agent_pid, "reason": reason})
        print(f"\n[WATCHDOG] Killing cursor-agent (PID {agent_pid}): {reason}", file=sys.stderr)
        try:
            os.kill(agent_pid, signal.SIGTERM)
            time.sleep(2)
            os.kill(agent_pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def process_line(line: str):
    """Process a single line of stream-json output."""
    global last_output_time, taxonomy_edited, tool_calls, file_edits, shell_calls

    last_output_time = time.time()

    if not line.strip():
        return

    # Try to parse as JSON
    try:
        event = json.loads(line.strip())
    except json.JSONDecodeError:
        # Not JSON — just regular output, still counts as activity
        return

    event_type = event.get("type", "")

    # ── Tool call detection ──────────────────────────────────────
    if event_type in ("tool_use", "tool_call", "tool_result"):
        tool_calls += 1
        tool_name = event.get("name", event.get("tool", ""))

        # Detect file edits on taxonomy.json
        if tool_name in ("Write", "Edit", "edit", "write"):
            file_path = event.get("input", {}).get("file_path", "")
            if not file_path:
                file_path = event.get("input", {}).get("path", "")
            if "taxonomy.json" in str(file_path):
                taxonomy_edited = True
                file_edits += 1
                log_event("taxonomy_edit", {"tool": tool_name, "edit_num": file_edits})

                # Auto-validate after taxonomy edit
                metrics = run_validate()
                if metrics:
                    log_metrics(metrics)
                    nliv = metrics.get("nliv_mean", "?")
                    csc = metrics.get("csc_score", "?")
                    comp = metrics.get("composite_score", "?")
                    nodes = metrics.get("node_count", "?")
                    print(f"[MONITOR] Auto-validate: NLIV={nliv} CSC={csc} Composite={comp} nodes={nodes}",
                          file=sys.stderr)

        # Detect shell executions
        if tool_name in ("Shell", "Bash", "bash", "shell", "terminal"):
            shell_calls += 1
            cmd = event.get("input", {}).get("command", "")[:100]
            log_event("shell_call", {"command": cmd})

        # Detect taxonomy.json reads (budget warning)
        if tool_name in ("Read", "read", "Cat", "cat"):
            file_path = event.get("input", {}).get("file_path", "")
            if "taxonomy.json" in str(file_path):
                log_event("taxonomy_full_read", {"warning": "Full taxonomy.json read detected"})
                print("[MONITOR] WARNING: Full taxonomy.json read (consider using CLI tree/stats instead)",
                      file=sys.stderr)

    # ── Content/thinking detection (for watchdog) ────────────────
    elif event_type in ("content_block_delta", "thinking_delta", "text_delta", "message_delta"):
        pass  # Already updated last_output_time above

    # ── Message completion ───────────────────────────────────────
    elif event_type in ("message_stop", "result"):
        log_event("message_complete", {
            "tool_calls": tool_calls,
            "file_edits": file_edits,
            "shell_calls": shell_calls,
            "taxonomy_edited": taxonomy_edited
        })


def main():
    global agent_pid, last_output_time

    parser = argparse.ArgumentParser(description="Stream monitor for cursor-agent")
    parser.add_argument("--pid", type=int, help="cursor-agent PID to watchdog")
    parser.add_argument("--timeout", type=int, default=SILENCE_TIMEOUT,
                        help=f"Silence timeout in seconds (default: {SILENCE_TIMEOUT})")
    args = parser.parse_args()

    agent_pid = args.pid
    silence_timeout = args.timeout

    log_event("monitor_start", {"pid": agent_pid, "silence_timeout": silence_timeout})

    # Read from stdin (piped from cursor-agent)
    import select

    try:
        while True:
            # Check if there's data available (poll every 1 second)
            if select.select([sys.stdin], [], [], 1.0)[0]:
                line = sys.stdin.readline()
                if not line:
                    # EOF — agent finished
                    break
                process_line(line)
            else:
                # No data — check watchdog
                silence_secs = time.time() - last_output_time
                if silence_secs > silence_timeout:
                    kill_agent(f"No output for {int(silence_secs)}s (limit: {silence_timeout}s)")
                    break

                # Also check if agent process is still alive
                if agent_pid:
                    try:
                        os.kill(agent_pid, 0)  # Signal 0 = check existence
                    except ProcessLookupError:
                        # Agent died
                        log_event("agent_died", {"pid": agent_pid})
                        break

    except KeyboardInterrupt:
        log_event("monitor_interrupt", {})

    # Final summary
    summary = {
        "tool_calls": tool_calls,
        "file_edits": file_edits,
        "shell_calls": shell_calls,
        "taxonomy_edited": taxonomy_edited,
    }
    log_event("monitor_stop", summary)

    # If taxonomy was edited, run final validation
    if taxonomy_edited:
        metrics = run_validate()
        if metrics:
            log_metrics(metrics)
            summary["final_metrics"] = metrics

    # Print summary to stderr
    print(f"\n[MONITOR] Session summary: {json.dumps(summary)}", file=sys.stderr)


if __name__ == "__main__":
    main()
