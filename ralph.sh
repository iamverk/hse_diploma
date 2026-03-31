#!/bin/bash
#
# ralph.sh — Autonomous taxonomy builder loop.
# Adapted from https://github.com/snarktank/ralph
#
# Usage:
#   ./ralph.sh [max_iterations] [--tool claude|amp|cursor] [--model MODEL]
#
# Examples:
#   ./ralph.sh 10                                                  # claude (default)
#   ./ralph.sh 10 --tool cursor                                    # cursor, default model
#   ./ralph.sh 10 --tool cursor --model gpt-5.3-codex-spark-preview-xhigh
#   ./ralph.sh 5 --tool amp
#
# Each iteration:
#   1. Spawns a fresh AI agent (clean context each time)
#   2. Agent reads AGENTS.md (cursor) or CLAUDE.md (claude) + progress.txt + prd.json
#   3. Picks next unfinished story, implements it
#   4. Runs validate.py (stop hook)
#   5. Commits if valid, logs learnings to progress.txt
#   6. Repeats until all stories pass or max iterations reached

set -e

# ── Cursor Agent models ──────────────────────────────────────────────────────
#   gpt-5.3-codex-spark-preview-high   → GPT-5.3 Codex Spark High   (faster)
#   gpt-5.3-codex-spark-preview-xhigh  → GPT-5.3 Codex Spark Extra High (stronger)

# ── Defaults ────────────────────────────────────────────────────────────────
MAX_ITERATIONS=10
TOOL="claude"
MODEL="gpt-5.3-codex-spark-preview-high"

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
        [0-9]*)
            MAX_ITERATIONS="$1"; shift ;;
        *)
            echo "Unknown argument: $1"
            echo "Usage: ./ralph.sh [max_iterations] [--tool claude|amp|cursor] [--model MODEL]"
            exit 1 ;;
    esac
done

# ── Files ────────────────────────────────────────────────────────────────────
PRD_FILE="prd.json"
PROGRESS_FILE="progress.txt"
TAXONOMY_FILE="taxonomy.json"
PYTHON="/Users/iamverk/anaconda3/envs/taxonomy-as-code/bin/python"
LOG_DIR="results/logs"

echo "==========================================="
echo "  TAXONOMY RALPH LOOP"
echo "  Tool:           $TOOL"
echo "  Max iterations: $MAX_ITERATIONS"
if [ "$TOOL" = "cursor" ]; then
    echo "  Model:          $MODEL"
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
            echo "ERROR: claude CLI not found (npm install -g @anthropic-ai/claude-code)"
            exit 1
        fi ;;
    amp)
        if ! command -v amp &> /dev/null; then
            echo "ERROR: amp CLI not found"
            exit 1
        fi ;;
    cursor)
        if ! command -v cursor-agent &> /dev/null; then
            echo "ERROR: cursor-agent not found (curl https://cursor.com/install -fsSL | bash)"
            exit 1
        fi
        # Validate model choice
        VALID_MODELS="gpt-5.3-codex-spark-preview-high gpt-5.3-codex-spark-preview-xhigh"
        if [[ ! " $VALID_MODELS " =~ " $MODEL " ]]; then
            echo "ERROR: unsupported model '$MODEL'"
            echo "Available models:"
            echo "  gpt-5.3-codex-spark-preview-high   (GPT-5.3 Codex Spark High)"
            echo "  gpt-5.3-codex-spark-preview-xhigh  (GPT-5.3 Codex Spark Extra High)"
            exit 1
        fi ;;
    *)
        echo "ERROR: unknown tool '$TOOL'. Choose: claude | amp | cursor"
        exit 1 ;;
esac

# ── Git init if needed ───────────────────────────────────────────────────────
if [ ! -d ".git" ]; then
    git init
    git add -A
    git commit -m "Initial taxonomy setup"
fi

# ── Main loop ────────────────────────────────────────────────────────────────
# ── Init per-iteration log ────────────────────────────────────────────────────
mkdir -p "$LOG_DIR"
METRICS_CSV="$LOG_DIR/metrics_${TOOL}_$(date +%Y%m%d_%H%M%S).csv"
echo "iteration,story_id,story_title,passed,edge_f1,node_coverage,ancestor_f1,elapsed_sec" > "$METRICS_CSV"

for i in $(seq 1 $MAX_ITERATIONS); do
    ITER_START=$(date +%s)
    echo ""
    echo "--- Iteration $i / $MAX_ITERATIONS ---"

    # Check if all stories pass
    ALL_PASS=$(jq '[.userStories[].passes] | all' "$PRD_FILE")
    if [ "$ALL_PASS" = "true" ]; then
        echo "All stories completed! Exiting loop."
        break
    fi

    # Find first incomplete story
    CURRENT_STORY=$(jq -r '.userStories[] | select(.passes == false) | .title' "$PRD_FILE" | head -1)
    CURRENT_ID=$(jq -r '.userStories[] | select(.passes == false) | .id' "$PRD_FILE" | head -1)
    echo "Current task: [$CURRENT_ID] $CURRENT_STORY"

    # Snapshot taxonomy before this iteration
    cp "$TAXONOMY_FILE" "/tmp/taxonomy_before_iter_${i}.json"

    # ── Run the agent ────────────────────────────────────────────────────────
    if [ "$TOOL" = "claude" ]; then
        # Claude Code reads CLAUDE.md for its iteration workflow
        PROMPT="Read CLAUDE.md for instructions. Read progress.txt for learnings from previous iterations. Your current task from prd.json is: [$CURRENT_ID] $CURRENT_STORY. Complete this task, run validate.py, and if it passes, mark the story as passes:true in prd.json and append your learnings to progress.txt. Then commit."
        echo "$PROMPT" | claude --dangerously-skip-permissions

    elif [ "$TOOL" = "amp" ]; then
        PROMPT="Read CLAUDE.md for instructions. Read progress.txt for learnings from previous iterations. Your current task from prd.json is: [$CURRENT_ID] $CURRENT_STORY. Complete this task, run validate.py, and if it passes, mark the story as passes:true in prd.json and append your learnings to progress.txt. Then commit."
        echo "$PROMPT" | amp

    elif [ "$TOOL" = "cursor" ]; then
        # Cursor Agent reads AGENTS.md — its native instruction file
        CURSOR_PROMPT="Read AGENTS.md for instructions. Read progress.txt for learnings from previous iterations. Your current task from prd.json is: [$CURRENT_ID] $CURRENT_STORY. Complete this task, run validate.py, and if it passes, mark the story as passes:true in prd.json and append your learnings to progress.txt. Then commit."
        cursor-agent \
            --print \
            --model "$MODEL" \
            --yolo \
            --trust \
            --workspace . \
            "$CURSOR_PROMPT"
    fi

    # ── Check story completion ───────────────────────────────────────────────
    STORY_PASS=$(jq -r ".userStories[] | select(.id == $CURRENT_ID) | .passes" "$PRD_FILE")
    if [ "$STORY_PASS" = "true" ]; then
        echo "Story [$CURRENT_ID] completed successfully."

        # Log metrics to progress.txt
        echo "--- Metrics after iteration $i (story $CURRENT_ID) ---" >> "$PROGRESS_FILE"
        $PYTHON tools/metrics.py "$TAXONOMY_FILE" reference/gold_standard.json >> "$PROGRESS_FILE" 2>&1 || true
        echo "" >> "$PROGRESS_FILE"
    else
        echo "Story [$CURRENT_ID] not completed. Will retry next iteration."
        echo "--- Iteration $i FAILED for story [$CURRENT_ID] ---" >> "$PROGRESS_FILE"
        echo "Agent did not mark story as complete." >> "$PROGRESS_FILE"
        echo "" >> "$PROGRESS_FILE"
    fi

    # ── Per-iteration metrics to CSV ────────────────────────────────────────
    ITER_END=$(date +%s)
    ELAPSED=$((ITER_END - ITER_START))
    METRICS_RAW=$($PYTHON tools/metrics.py "$TAXONOMY_FILE" reference/gold_standard.json 2>/dev/null || echo "")
    EDGE_F1=$(echo "$METRICS_RAW" | grep -i "edge.*f1" | awk '{print $NF}' || echo "")
    NODE_COV=$(echo "$METRICS_RAW" | grep -i "node.*coverage" | awk '{print $NF}' || echo "")
    ANC_F1=$(echo "$METRICS_RAW" | grep -i "ancestor.*f1" | awk '{print $NF}' || echo "")
    echo "$i,$CURRENT_ID,\"$CURRENT_STORY\",$STORY_PASS,$EDGE_F1,$NODE_COV,$ANC_F1,$ELAPSED" >> "$METRICS_CSV"

    # Progress summary
    DONE=$(jq '[.userStories[] | select(.passes == true)] | length' "$PRD_FILE")
    TOTAL=$(jq '.userStories | length' "$PRD_FILE")
    echo "Progress: $DONE / $TOTAL stories complete"
done

# ── Final summary ─────────────────────────────────────────────────────────────
echo ""
echo "==========================================="
echo "  RALPH LOOP FINISHED"
echo "==========================================="
echo ""
$PYTHON tools/taxonomy_cli.py stats
echo ""
$PYTHON tools/metrics.py "$TAXONOMY_FILE" reference/gold_standard.json 2>/dev/null \
    || echo "(metrics unavailable)"

# ── Save experiment log ──────────────────────────────────────────────────────
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DOMAIN=$(jq -r '.domain // "unknown"' "$PRD_FILE" 2>/dev/null)
RUN_DIR="results/${TOOL}_${MODEL}_${DOMAIN}_${TIMESTAMP}"
mkdir -p "$RUN_DIR"
cp "$TAXONOMY_FILE"   "$RUN_DIR/final_taxonomy.json"
cp "$PRD_FILE"        "$RUN_DIR/prd.json"
cp "$PROGRESS_FILE"   "$RUN_DIR/progress.txt"
git log --oneline > "$RUN_DIR/git_log.txt" 2>/dev/null || true
$PYTHON tools/metrics.py "$TAXONOMY_FILE" reference/gold_standard.json > "$RUN_DIR/final_metrics.txt" 2>/dev/null || true

# Save config
cat > "$RUN_DIR/config.json" <<CFGEOF
{
  "tool": "$TOOL",
  "model": "$MODEL",
  "domain": "$DOMAIN",
  "max_iterations": $MAX_ITERATIONS,
  "actual_iterations": $i,
  "timestamp": "$TIMESTAMP"
}
CFGEOF

cp "$METRICS_CSV" "$RUN_DIR/metrics_per_iteration.csv"
echo ""
echo "Results saved to: $RUN_DIR/"
echo "Metrics CSV: $METRICS_CSV"
