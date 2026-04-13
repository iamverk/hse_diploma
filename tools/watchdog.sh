#!/bin/bash
#
# watchdog.sh — Process-level watchdog for cursor-agent
#
# Monitors cursor-agent by checking if its CHILD processes are active.
# When cursor-agent is thinking: node worker-server is active (CPU > 0 or state = running)
# When cursor-agent is stuck: node worker-server has 0% CPU and state = sleeping for extended period
#
# Usage: watchdog.sh <AGENT_PID> <TIMEOUT_SECS> <STREAM_FILE>
#
# Returns: 0 if agent finished normally, 1 if watchdog killed it

AGENT_PID="$1"
TIMEOUT="${2:-180}"
STREAM_FILE="${3:-/dev/null}"

if [ -z "$AGENT_PID" ]; then
    echo "[watchdog] ERROR: no PID provided" >&2
    exit 2
fi

IDLE_SECONDS=0
CHECK_INTERVAL=10
LAST_FILE_SIZE=0
LAST_ACTIVE_TIME=$(date +%s)

echo "[watchdog] Monitoring PID $AGENT_PID, timeout=${TIMEOUT}s" >&2

while kill -0 "$AGENT_PID" 2>/dev/null; do
    sleep "$CHECK_INTERVAL"

    # Method 1: Check file growth
    CURR_SIZE=0
    if [ -f "$STREAM_FILE" ]; then
        CURR_SIZE=$(wc -c < "$STREAM_FILE" 2>/dev/null || echo 0)
    fi

    # Method 2: Check if cursor-agent or its children have recent CPU usage
    # Get all child PIDs recursively
    CHILD_PIDS=$(pgrep -P "$AGENT_PID" 2>/dev/null)
    CPU_ACTIVE=false
    for cpid in $CHILD_PIDS $(pgrep -P $CHILD_PIDS 2>/dev/null); do
        CPU=$(ps -p "$cpid" -o %cpu= 2>/dev/null | tr -d ' ')
        if [ -n "$CPU" ] && [ "$(echo "$CPU > 0.5" | bc 2>/dev/null || echo 0)" = "1" ]; then
            CPU_ACTIVE=true
            break
        fi
    done

    # Method 3: Check if taxonomy.json was recently modified
    TAX_MTIME=0
    if [ -f "taxonomy.json" ]; then
        TAX_MTIME=$(stat -f %m taxonomy.json 2>/dev/null || echo 0)
    fi

    # Method 4: Check git for new commits
    CURR_HEAD=$(git rev-parse HEAD 2>/dev/null || echo "")

    # Determine if agent is active
    FILE_GREW=false
    if [ "$CURR_SIZE" -gt "$LAST_FILE_SIZE" ]; then
        FILE_GREW=true
        LAST_FILE_SIZE=$CURR_SIZE
    fi

    if [ "$FILE_GREW" = true ] || [ "$CPU_ACTIVE" = true ]; then
        LAST_ACTIVE_TIME=$(date +%s)
        IDLE_SECONDS=0

        # Activity report every 60s
        ELAPSED=$(( $(date +%s) - LAST_ACTIVE_TIME + CHECK_INTERVAL ))
        TOTAL_ELAPSED=$(ps -p "$AGENT_PID" -o etime= 2>/dev/null | tr -d ' ')
        LINES=$(wc -l < "$STREAM_FILE" 2>/dev/null || echo 0)
        if [ $((IDLE_SECONDS % 60)) -lt $CHECK_INTERVAL ]; then
            echo "[watchdog] Active: ${LINES} events, ${CURR_SIZE} bytes, CPU_active=${CPU_ACTIVE} (elapsed: ${TOTAL_ELAPSED})" >&2
        fi
    else
        NOW=$(date +%s)
        IDLE_SECONDS=$((NOW - LAST_ACTIVE_TIME))

        if [ "$IDLE_SECONDS" -ge "$TIMEOUT" ]; then
            echo "[watchdog] KILL: idle for ${IDLE_SECONDS}s (file_grew=false, CPU_active=false)" >&2
            kill "$AGENT_PID" 2>/dev/null
            sleep 2
            kill -9 "$AGENT_PID" 2>/dev/null
            # Also kill children
            for cpid in $(pgrep -P "$AGENT_PID" 2>/dev/null); do
                kill -9 "$cpid" 2>/dev/null
            done
            exit 1
        fi

        # Warn at 50%
        HALF=$((TIMEOUT / 2))
        if [ "$IDLE_SECONDS" -ge "$HALF" ]; then
            echo "[watchdog] WARNING: idle ${IDLE_SECONDS}s / ${TIMEOUT}s (file_grew=false, CPU=${CPU_ACTIVE})" >&2
        fi
    fi
done

echo "[watchdog] Agent finished normally" >&2
exit 0
