#!/bin/bash
#
# ralph.sh — Autonomous taxonomy builder loop v9 (stream-monitor + watchdog).
#
# Improvements over v8:
#   - Stream-JSON monitor: parses cursor-agent output in real-time
#   - Watchdog: kills agent if no output for 5 minutes (fixes 17h hang)
#   - Only CLI-working hooks kept (beforeShellExecution, afterFileEdit)
#   - Removed broken hooks (beforeReadFile, stop)
#   - Auto-validate via stream monitor (not dependent on afterFileEdit hook)
#
# Usage:
#   ./ralph.sh [max_iterations] [--tool claude|amp|cursor] [--model MODEL]

trap '' HUP  # Ignore SIGHUP — survive laptop lid close

# ── Ensure homebrew tools (jq, etc.) are in PATH ────────────────────────────
export PATH="/Users/iamverk/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

# ── Defaults ────────────────────────────────────────────────────────────────
MAX_ITERATIONS=40
TOOL="cursor"
MODEL="gpt-5.3-codex-spark-preview-high"
WATCHDOG_TIMEOUT=300  # 5 minutes silence → kill

# ── Parse arguments ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --tool)
            TOOL="$2"; shift 2 ;;
        --tool=*)
            TOOL="${1#*=}"; shift ;;
        --model)
            MODEL="$2"; shift 2 ;;
        --model=*)
            MODEL="${1#*=}"; shift ;;
        --watchdog)
            WATCHDOG_TIMEOUT="$2"; shift 2 ;;
        [0-9]*)
            MAX_ITERATIONS="$1"; shift ;;
        *)
            echo "Unknown argument: $1"
            echo "Usage: ./ralph.sh [max_iterations] [--tool claude|amp|cursor] [--model MODEL] [--watchdog SECS]"
            exit 1 ;;
    esac
done

# ── Files ────────────────────────────────────────────────────────────────────
PRD_FILE="prd.json"
PROGRESS_FILE="progress.txt"
TAXONOMY_FILE="taxonomy.json"
PYTHON="/Users/iamverk/anaconda3/envs/taxonomy-as-code/bin/python"
export PYTHON  # stream_monitor.py uses this
LOG_DIR="results/logs"
HISTORY_DIR="output/taxonomy_history"
STREAM_MONITOR="tools/stream_monitor.py"

STUCK_FILE="output/stuck_domains.txt"
ROLLBACK_COUNTS="output/rollback_counts.json"

echo "==========================================="
echo "  TAXONOMY RALPH LOOP (v9 — stream-monitor+watchdog)"
echo "  Tool:              $TOOL"
echo "  Max iterations:    $MAX_ITERATIONS"
echo "  Watchdog timeout:  ${WATCHDOG_TIMEOUT}s"
if [ "$TOOL" = "cursor" ]; then
    echo "  Model:             $MODEL"
fi
echo "==========================================="

# ── Prerequisites ────────────────────────────────────────────────────────────
if [ ! -f "$PRD_FILE" ]; then
    echo "ERROR: $PRD_FILE not found"
    exit 1
fi

if ! command -v jq &> /dev/null; then
    echo "ERROR: jq is required (brew install jq)"
    exit 1
fi

case "$TOOL" in
    claude)
        if ! command -v claude &> /dev/null; then
            echo "ERROR: claude CLI not found"
            exit 1
        fi ;;
    amp)
        if ! command -v amp &> /dev/null; then
            echo "ERROR: amp CLI not found"
            exit 1
        fi ;;
    cursor)
        if ! command -v cursor-agent &> /dev/null; then
            echo "ERROR: cursor-agent not found"
            exit 1
        fi
        VALID_MODELS="gpt-5.3-codex-spark-preview-high gpt-5.3-codex-spark-preview-xhigh"
        if [[ ! " $VALID_MODELS " =~ " $MODEL " ]]; then
            echo "ERROR: unsupported model '$MODEL'"
            exit 1
        fi ;;
    *)
        echo "ERROR: unknown tool '$TOOL'"
        exit 1 ;;
esac

# ── Git init if needed ───────────────────────────────────────────────────────
if [ ! -d ".git" ]; then
    git init
    git add -A
    git commit -m "Initial taxonomy setup"
fi

# ── Auto-archive previous run if iteration_log exists ────────────────────────
if [ -f "output/iteration_log.jsonl" ]; then
    ARCHIVE_TS=$(date +%Y%m%d_%H%M%S)
    ARCHIVE_DIR="output/archive/${ARCHIVE_TS}"
    mkdir -p "$ARCHIVE_DIR"
    cp "$PRD_FILE" "$ARCHIVE_DIR/" 2>/dev/null || true
    cp "$PROGRESS_FILE" "$ARCHIVE_DIR/" 2>/dev/null || true
    cp "$TAXONOMY_FILE" "$ARCHIVE_DIR/" 2>/dev/null || true
    cp "output/iteration_log.jsonl" "$ARCHIVE_DIR/" 2>/dev/null || true
    cp "output/stream_events.jsonl" "$ARCHIVE_DIR/" 2>/dev/null || true
    cp "output/hook_metrics.jsonl" "$ARCHIVE_DIR/" 2>/dev/null || true
    echo "Archived previous run to $ARCHIVE_DIR/"
fi

# ── Create output directories ────────────────────────────────────────────────
mkdir -p "$LOG_DIR" "$HISTORY_DIR" "output"

# ── Clear logs for fresh run ────────────────────────────────────────────────
> "output/iteration_log.jsonl"
> "output/stream_events.jsonl"
> "output/hook_metrics.jsonl"

# ── Init per-run CSV log ─────────────────────────────────────────────────────
METRICS_CSV="$LOG_DIR/metrics_${TOOL}_$(date +%Y%m%d_%H%M%S).csv"
echo "iteration,story_id,story_title,passed,status,nliv_mean,csc_score,composite,sem_edge_f1,node_count,elapsed_sec" > "$METRICS_CSV"

# ── Track previous composite for rollback ────────────────────────────────────
PREV_COMPOSITE=""

# ── Main loop ────────────────────────────────────────────────────────────────
for i in $(seq 1 $MAX_ITERATIONS); do
    ITER_START=$(date +%s)
    echo ""
    echo "╔══════════════════════════════════════════╗"
    echo "║  Iteration $i / $MAX_ITERATIONS"
    echo "╚══════════════════════════════════════════╝"

    # Check if all stories pass
    ALL_PASS=$(jq '[.userStories[].passes] | all' "$PRD_FILE")
    if [ "$ALL_PASS" = "true" ]; then
        echo "✓ All stories completed! Exiting loop."
        break
    fi

    # Find first incomplete story
    CURRENT_STORY=$(jq -r '.userStories[] | select(.passes == false) | .title' "$PRD_FILE" | head -1)
    CURRENT_ID=$(jq -r '.userStories[] | select(.passes == false) | .id' "$PRD_FILE" | head -1)
    echo "▸ Current task: [Story $CURRENT_ID] $CURRENT_STORY"

    # ── Stuck-domain auto-skip ──────────────────────────────────────────
    if [ -f "$STUCK_FILE" ]; then
        DOMAIN_NAME=$(echo "$CURRENT_STORY" | grep -oP '(?:Expand|Refine|Fix).*?:\s*\K\S+' 2>/dev/null || echo "")
        if [ -n "$DOMAIN_NAME" ] && grep -qw "$DOMAIN_NAME" "$STUCK_FILE" 2>/dev/null; then
            echo "⏭ SKIP: Domain '$DOMAIN_NAME' is in stuck_domains.txt (3+ consecutive rollbacks)"
            jq "(.userStories[] | select(.id == $CURRENT_ID)) .passes = true | (.userStories[] | select(.id == $CURRENT_ID)) .notes = \"skipped — CSC metric ceiling\"" "$PRD_FILE" > "${PRD_FILE}.tmp" && mv "${PRD_FILE}.tmp" "$PRD_FILE"
            git add -A && git commit -m "story $CURRENT_ID: skip $DOMAIN_NAME — CSC metric ceiling" 2>/dev/null || true
            echo "$i,$CURRENT_ID,\"$CURRENT_STORY\",true,skip,N/A,N/A,N/A,N/A,N/A,0" >> "$METRICS_CSV"
            continue
        fi
    fi

    # Snapshot taxonomy before this iteration
    cp "$TAXONOMY_FILE" "$HISTORY_DIR/taxonomy_iter_${i}_before.json"

    # Record git HEAD before agent runs (for potential rollback)
    HEAD_BEFORE=$(git rev-parse HEAD 2>/dev/null || echo "")

    # ── Build agent prompt ───────────────────────────────────────────────────
    PROMPT="Read AGENTS.md for instructions. Read progress.txt for context and discovered patterns. Your current task from prd.json is: [Story $CURRENT_ID] $CURRENT_STORY. IMPORTANT: Work on THIS ONE STORY ONLY. You have an embedder: $PYTHON tools/check_edge.py 'parent' 'child' — use it to verify NLIV BEFORE adding edges. Use grep for product discovery, embedder for validation. Complete this task, run validate.py to check quality, fix any issues, and if acceptance criteria are met, mark the story as passes:true in prd.json. Update progress.txt: overwrite the ## Current State section but PRESERVE the ## Discovered Patterns section at the top — only add new patterns if you discover something reusable. Then commit with message 'story $CURRENT_ID: <description>'."

    # ── Run the agent ────────────────────────────────────────────────────────
    ITER_STATUS="keep"  # default; changed to discard/crash below

    if [ "$TOOL" = "claude" ]; then
        echo "$PROMPT" | claude --dangerously-skip-permissions
        AGENT_EXIT=$?

    elif [ "$TOOL" = "amp" ]; then
        echo "$PROMPT" | amp
        AGENT_EXIT=$?

    elif [ "$TOOL" = "cursor" ]; then
        # ── Stream-JSON + mtime watchdog ────────────────────────────────
        STREAM_FILE="output/cursor_stream_iter${i}.jsonl"
        > "$STREAM_FILE"  # clear

        # Launch cursor-agent, tee output to stream file
        cursor-agent \
            --print \
            --output-format stream-json \
            --stream-partial-output \
            --model "$MODEL" \
            --yolo \
            --trust \
            --workspace . \
            "$PROMPT" 2>"output/cursor_stderr_iter${i}.log" | \
        tee "$STREAM_FILE" > /dev/null &
        PIPE_PID=$!

        sleep 3
        AGENT_PID=$(pgrep -f "cursor-agent.*stream-json" 2>/dev/null | head -1)
        echo "  [watchdog] cursor-agent PID=$AGENT_PID, tee PID=$PIPE_PID"
        echo "  [watchdog] Stream file: $STREAM_FILE"
        echo "  [watchdog] Silence timeout: ${WATCHDOG_TIMEOUT}s, Hard timeout: 2700s (45 min)"

        # ── Watchdog loop: mtime-based silence detection ────────────────
        WAIT_SECS=0
        HARD_TIMEOUT=2700  # 45 min — real guard is silence watchdog
        LAST_SIZE=0
        SILENCE_START=$SECONDS

        while kill -0 $PIPE_PID 2>/dev/null; do
            sleep 10
            WAIT_SECS=$((WAIT_SECS + 10))

            # Hard timeout (25 min absolute)
            if [ $WAIT_SECS -ge $HARD_TIMEOUT ]; then
                echo "  [watchdog] HARD TIMEOUT: ${HARD_TIMEOUT}s exceeded"
                ITER_STATUS="crash"
                break
            fi

            # Check if stream file grew (silence detection)
            CURR_SIZE=$(wc -c < "$STREAM_FILE" 2>/dev/null || echo "0")
            if [ "$CURR_SIZE" -gt "$LAST_SIZE" ]; then
                LAST_SIZE=$CURR_SIZE
                SILENCE_START=$SECONDS
                # Print activity indicator every 60s
                if [ $((WAIT_SECS % 60)) -eq 0 ]; then
                    LINES=$(wc -l < "$STREAM_FILE" 2>/dev/null || echo "0")
                    echo "  [watchdog] Active: ${LINES} stream events, ${CURR_SIZE} bytes (${WAIT_SECS}s elapsed)"
                fi
            else
                SILENCE_SECS=$((SECONDS - SILENCE_START))
                if [ "$SILENCE_SECS" -ge "$WATCHDOG_TIMEOUT" ]; then
                    echo "  [watchdog] SILENCE KILL: no output for ${SILENCE_SECS}s (limit: ${WATCHDOG_TIMEOUT}s)"
                    ITER_STATUS="crash"
                    break
                fi
                # Warn at 50% silence threshold
                HALF_TIMEOUT=$((WATCHDOG_TIMEOUT / 2))
                if [ "$SILENCE_SECS" -ge "$HALF_TIMEOUT" ] && [ $((SILENCE_SECS % 30)) -lt 10 ]; then
                    echo "  [watchdog] WARNING: silent for ${SILENCE_SECS}s / ${WATCHDOG_TIMEOUT}s"
                fi
            fi
        done

        # Kill cursor-agent if watchdog triggered
        if [ "$ITER_STATUS" = "crash" ]; then
            [ -n "$AGENT_PID" ] && kill $AGENT_PID 2>/dev/null
            kill $PIPE_PID 2>/dev/null
            sleep 2
            [ -n "$AGENT_PID" ] && kill -9 $AGENT_PID 2>/dev/null
            kill -9 $PIPE_PID 2>/dev/null
        fi

        wait $PIPE_PID 2>/dev/null
        AGENT_EXIT=$?

        # Post-process stream file
        STREAM_SIZE=$(wc -c < "$STREAM_FILE" 2>/dev/null || echo "0")
        STREAM_LINES=$(wc -l < "$STREAM_FILE" 2>/dev/null || echo "0")
        echo "  [stream] File: ${STREAM_LINES} lines, ${STREAM_SIZE} bytes"

        if [ "$STREAM_SIZE" -gt 0 ]; then
            $PYTHON "$STREAM_MONITOR" "$STREAM_FILE" 2>/dev/null || true
        fi
    fi

    # Check if agent crashed
    if [ "${AGENT_EXIT:-0}" -ne 0 ] && [ "$ITER_STATUS" != "crash" ]; then
        echo "⚠ Agent exited with code $AGENT_EXIT"
        if ! git diff --quiet "$TAXONOMY_FILE" 2>/dev/null; then
            echo "  (taxonomy was modified, treating as partial success)"
        else
            ITER_STATUS="crash"
        fi
    fi

    # ── Post-iteration: snapshot ─────────────────────────────────────────────
    cp "$TAXONOMY_FILE" "$HISTORY_DIR/taxonomy_iter_${i}_after.json"

    # ── Collect metrics ──────────────────────────────────────────────────────
    ITER_END=$(date +%s)
    ELAPSED=$((ITER_END - ITER_START))

    # Reference-free metrics (NLIV/CSC)
    V2_RAW=$($PYTHON tools/metrics_v2.py "$TAXONOMY_FILE" --json 2>/dev/null || echo "{}")
    NLIV_MEAN=$(echo "$V2_RAW" | jq -r '.nliv_mean // "N/A"' 2>/dev/null || echo "N/A")
    CSC_SCORE=$(echo "$V2_RAW" | jq -r '.csc_score // "N/A"' 2>/dev/null || echo "N/A")
    COMPOSITE=$(echo "$V2_RAW" | jq -r '.composite_score // "N/A"' 2>/dev/null || echo "N/A")
    NODE_COUNT=$(echo "$V2_RAW" | jq -r '.node_count // "N/A"' 2>/dev/null || echo "N/A")

    # Reference-based metrics (Edge F1 vs gold — post-hoc only)
    GOLD_PATH="/Users/iamverk/Desktop/HSE/diploma/.hidden_eval/gold_standard.json"
    METRICS_RAW=$($PYTHON tools/metrics.py "$TAXONOMY_FILE" "$GOLD_PATH" 2>/dev/null || echo "")
    SEM_F1=$(echo "$METRICS_RAW" | grep -i "^Sem Edge F1" | head -1 | awk '{print $NF}')
    [ -z "$SEM_F1" ] && SEM_F1="N/A"

    # ── ROLLBACK CHECK: did composite score degrade? ─────────────────────────
    if [ "$ITER_STATUS" != "crash" ] && [ -n "$PREV_COMPOSITE" ] && [ "$COMPOSITE" != "N/A" ]; then
        SHOULD_ROLLBACK=$($PYTHON -c "
prev = $PREV_COMPOSITE
curr = $COMPOSITE
# Rollback if composite dropped by more than 0.02 (tolerance for noise)
print('yes' if curr < prev - 0.02 else 'no')
" 2>/dev/null || echo "no")

        if [ "$SHOULD_ROLLBACK" = "yes" ]; then
            echo "⚠ COMPOSITE DEGRADED: $PREV_COMPOSITE → $COMPOSITE (Δ > 0.02)"
            echo "  Rolling back to HEAD before this iteration..."
            HEAD_AFTER=$(git rev-parse HEAD 2>/dev/null || echo "")
            if [ -n "$HEAD_BEFORE" ] && [ "$HEAD_BEFORE" != "$HEAD_AFTER" ]; then
                git reset --hard "$HEAD_BEFORE"
                cp "$HISTORY_DIR/taxonomy_iter_${i}_before.json" "$TAXONOMY_FILE"
                ITER_STATUS="discard"
                echo "  ✓ Rolled back to $HEAD_BEFORE"
            else
                echo "  (no new commits to roll back — agent may not have committed)"
                ITER_STATUS="discard"
            fi
        fi
    fi

    # ── Update rollback counts for stuck-domain detection ──────────────
    DOMAIN_NAME=$(echo "$CURRENT_STORY" | grep -oP '(?:Expand|Refine|Fix).*?:\s*\K\S+' 2>/dev/null || echo "")
    if [ -n "$DOMAIN_NAME" ]; then
        [ ! -f "$ROLLBACK_COUNTS" ] && echo '{}' > "$ROLLBACK_COUNTS"
        if [ "$ITER_STATUS" = "discard" ] || [ "$ITER_STATUS" = "crash" ]; then
            CURR_COUNT=$(jq -r ".[\"$DOMAIN_NAME\"] // 0" "$ROLLBACK_COUNTS" 2>/dev/null || echo "0")
            NEW_COUNT=$((CURR_COUNT + 1))
            jq ".[\"$DOMAIN_NAME\"] = $NEW_COUNT" "$ROLLBACK_COUNTS" > "${ROLLBACK_COUNTS}.tmp" && mv "${ROLLBACK_COUNTS}.tmp" "$ROLLBACK_COUNTS"
            if [ "$NEW_COUNT" -ge 3 ]; then
                echo "$DOMAIN_NAME" >> "$STUCK_FILE"
                sort -u "$STUCK_FILE" -o "$STUCK_FILE" 2>/dev/null || true
                echo "⚠ Domain '$DOMAIN_NAME' marked as stuck ($NEW_COUNT consecutive failures)"
            fi
        elif [ "$ITER_STATUS" = "keep" ]; then
            jq ".[\"$DOMAIN_NAME\"] = 0" "$ROLLBACK_COUNTS" > "${ROLLBACK_COUNTS}.tmp" && mv "${ROLLBACK_COUNTS}.tmp" "$ROLLBACK_COUNTS" 2>/dev/null || true
        fi
    fi

    # Update previous composite for next iteration (only if kept)
    if [ "$ITER_STATUS" = "keep" ] && [ "$COMPOSITE" != "N/A" ]; then
        PREV_COMPOSITE="$COMPOSITE"
    fi

    # ── Check story completion ───────────────────────────────────────────────
    STORY_PASS=$(jq -r ".userStories[] | select(.id == $CURRENT_ID) | .passes" "$PRD_FILE")
    if [ "$STORY_PASS" = "true" ] && [ "$ITER_STATUS" = "keep" ]; then
        echo "✓ Story [$CURRENT_ID] completed successfully."
    elif [ "$ITER_STATUS" = "discard" ]; then
        echo "✗ Story [$CURRENT_ID] iteration discarded (quality regression)."
    elif [ "$ITER_STATUS" = "crash" ]; then
        echo "✗ Story [$CURRENT_ID] iteration crashed."
    else
        echo "▸ Story [$CURRENT_ID] not completed. Will retry next iteration."
    fi

    # ── Log to CSV (with status column) ──────────────────────────────────────
    echo "$i,$CURRENT_ID,\"$CURRENT_STORY\",$STORY_PASS,$ITER_STATUS,$NLIV_MEAN,$CSC_SCORE,$COMPOSITE,$SEM_F1,$NODE_COUNT,$ELAPSED" >> "$METRICS_CSV"

    # ── Log stream monitor stats ─────────────────────────────────────────────
    STREAM_STATS=$(tail -1 "output/stream_events.jsonl" 2>/dev/null || echo "{}")
    echo "  [stream] $STREAM_STATS"

    # ── Check convergence ────────────────────────────────────────────────────
    CONV_OUTPUT=$($PYTHON tools/convergence.py 2>/dev/null || echo '{"stop": false}')
    CONV_STOP=$(echo "$CONV_OUTPUT" | jq -r '.stop' 2>/dev/null || echo "false")
    CONV_REASON=$(echo "$CONV_OUTPUT" | jq -r '.reason' 2>/dev/null || echo "")

    if [ "$CONV_STOP" = "true" ]; then
        echo ">>> CONVERGED at iteration $i: $CONV_REASON"
        break
    fi

    # Progress summary
    DONE=$(jq '[.userStories[] | select(.passes == true)] | length' "$PRD_FILE")
    TOTAL=$(jq '.userStories | length' "$PRD_FILE")
    echo "Progress: $DONE/$TOTAL stories | NLIV=$NLIV_MEAN CSC=$CSC_SCORE Comp=$COMPOSITE | Status=$ITER_STATUS | Elapsed=${ELAPSED}s"
done

# ── Final summary ─────────────────────────────────────────────────────────────
echo ""
echo "==========================================="
echo "  RALPH LOOP FINISHED"
echo "==========================================="
echo ""
$PYTHON tools/taxonomy_cli.py stats 2>/dev/null || true
echo ""
echo "--- Reference-free metrics (NLIV/CSC) ---"
$PYTHON tools/metrics_v2.py "$TAXONOMY_FILE" 2>/dev/null || echo "(metrics_v2 unavailable)"
echo ""
echo "--- Reference-based metrics (Edge F1 vs gold) ---"
$PYTHON tools/metrics.py "$TAXONOMY_FILE" "$GOLD_PATH" 2>/dev/null || echo "(metrics unavailable)"

# ── Count keep/discard/crash ─────────────────────────────────────────────────
echo ""
echo "--- Iteration Stats ---"
KEEP_COUNT=$(grep -c ",keep," "$METRICS_CSV" 2>/dev/null || echo "0")
DISCARD_COUNT=$(grep -c ",discard," "$METRICS_CSV" 2>/dev/null || echo "0")
CRASH_COUNT=$(grep -c ",crash," "$METRICS_CSV" 2>/dev/null || echo "0")
SKIP_COUNT=$(grep -c ",skip," "$METRICS_CSV" 2>/dev/null || echo "0")
echo "Keep: $KEEP_COUNT | Discard: $DISCARD_COUNT | Crash: $CRASH_COUNT | Skip: $SKIP_COUNT"

# ── Stream monitor summary ───────────────────────────────────────────────────
echo ""
echo "--- Stream Monitor Stats ---"
if [ -f "output/stream_events.jsonl" ]; then
    TOTAL_EVENTS=$(wc -l < "output/stream_events.jsonl" 2>/dev/null || echo "0")
    WATCHDOG_KILLS=$(grep -c '"watchdog_kill"' "output/stream_events.jsonl" 2>/dev/null || echo "0")
    TAX_EDITS=$(grep -c '"taxonomy_edit"' "output/stream_events.jsonl" 2>/dev/null || echo "0")
    echo "Events: $TOTAL_EVENTS | Watchdog kills: $WATCHDOG_KILLS | Taxonomy edits: $TAX_EDITS"
fi

# ── Save experiment log ──────────────────────────────────────────────────────
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DOMAIN=$(jq -r '.domain // "unknown"' "$PRD_FILE" 2>/dev/null)
RUN_DIR="results/${TOOL}_${MODEL}_${DOMAIN}_${TIMESTAMP}"
mkdir -p "$RUN_DIR"
cp "$TAXONOMY_FILE"   "$RUN_DIR/final_taxonomy.json"
cp "$PRD_FILE"        "$RUN_DIR/prd.json"
cp "$PROGRESS_FILE"   "$RUN_DIR/progress.txt"
git log --oneline > "$RUN_DIR/git_log.txt" 2>/dev/null || true
$PYTHON tools/metrics.py "$TAXONOMY_FILE" "$GOLD_PATH" > "$RUN_DIR/final_metrics.txt" 2>/dev/null || true
$PYTHON tools/metrics_v2.py "$TAXONOMY_FILE" > "$RUN_DIR/final_metrics_v2.txt" 2>/dev/null || true
cp output/iteration_log.jsonl "$RUN_DIR/iteration_log.jsonl" 2>/dev/null || true
cp output/stream_events.jsonl "$RUN_DIR/stream_events.jsonl" 2>/dev/null || true
cp output/hook_metrics.jsonl "$RUN_DIR/hook_metrics.jsonl" 2>/dev/null || true

cat > "$RUN_DIR/config.json" <<CFGEOF
{
  "tool": "$TOOL",
  "model": "$MODEL",
  "domain": "$DOMAIN",
  "max_iterations": $MAX_ITERATIONS,
  "actual_iterations": $i,
  "watchdog_timeout": $WATCHDOG_TIMEOUT,
  "timestamp": "$TIMESTAMP",
  "experiment": "v9-stream-watchdog"
}
CFGEOF

cp "$METRICS_CSV" "$RUN_DIR/metrics_per_iteration.csv"
echo ""
echo "Results saved to: $RUN_DIR/"
echo "Metrics CSV: $METRICS_CSV"
