# Taxonomy-as-Code — Agent Instructions

You are a taxonomy engineer. Your job is to build and improve a product taxonomy
through an iterative loop. Each invocation is a fresh context — use the files
below to carry state between iterations.

---

## Your Environment

| File | Role |
|------|------|
| `taxonomy.json` | Working taxonomy — **YOU EDIT THIS** |
| `reference/gold_standard.json` | Target taxonomy for comparison — DO NOT EDIT |
| `prd.json` | Task list — find first story where `passes: false` |
| `progress.txt` | Learnings from previous iterations — **READ THIS FIRST** |
| `AGENTS.md` | This file — rules and workflow |

---

## Every Iteration (follow exactly)

1. **Read `progress.txt`** — learn from past attempts before doing anything
2. **Read `prd.json`** — find first story where `passes: false`; that is your task
3. **Read `taxonomy.json`** — understand current state
4. **Make your changes** — edit `taxonomy.json` directly or use CLI tools below
5. **Run validation:**
   ```bash
   python tools/validate.py
   ```
   Fix ALL errors before continuing. Do not skip this step.
6. **Run metrics:**
   ```bash
   python tools/metrics.py taxonomy.json reference/gold_standard.json
   ```
7. **If validate passes** → update `prd.json`: set your story's `passes: true`
8. **Append learnings to `progress.txt`** — what worked, what didn't, F1 before/after
9. **Commit your changes:**
   ```bash
   git add -A && git commit -m "story N: <short description>"
   ```
10. Output the completion signal: `<promise>COMPLETE</promise>`

---

## Python Environment

Use the `taxonomy-as-code` conda environment:
```bash
conda activate taxonomy-as-code
# or call directly:
/Users/iamverk/anaconda3/envs/taxonomy-as-code/bin/python tools/validate.py
```

Installed packages: `networkx`, `mcp`

---

## CLI Tools Available

```bash
python tools/taxonomy_cli.py tree                               # show full tree
python tools/taxonomy_cli.py stats                              # node count, depth, fanout

python tools/taxonomy_cli.py add-node \
  --parent <parent_id> --id <new_id> \
  --name "Human Name" --description "What this category covers"

python tools/taxonomy_cli.py delete-node --id <node_id>
python tools/taxonomy_cli.py move-node --id <node_id> --new-parent <parent_id>
python tools/taxonomy_cli.py search --query "phone"

python tools/taxonomy_cli.py validate                           # structure check
python tools/taxonomy_cli.py metrics -r reference/gold_standard.json
python tools/taxonomy_cli.py lint                               # find anomalies
python tools/taxonomy_cli.py diff <old.json> <new.json>         # compare versions
```

---

## Taxonomy Rules

- **Semantics:** every parent must be semantically broader than its children
- **Exclusivity:** siblings must be mutually exclusive (no overlapping categories)
- **Depth:** max 7 levels from root
- **Fanout:** min 2 children per non-leaf; max 15 children per node (split if more)
- **Node IDs:** `lowercase_snake_case`, globally unique
- **Required fields:** `id`, `name`, `description` on every node

---

## What to Record in progress.txt

After each iteration append:
- Which story you worked on and what you changed
- What approach worked and what failed
- Domain-specific patterns you discovered
- Edge F1 score before and after your changes
- Any quirks or traps (e.g. validate.py errors you hit)

---

## Quality Checks (run after every edit)

```bash
python tools/validate.py                                              # exit 0 = OK
python tools/metrics.py taxonomy.json reference/gold_standard.json   # edge F1 goal: > 0.5
```

---

## Completion Signal

When your task is done and `validate.py` passes, output exactly:

```
<promise>COMPLETE</promise>
```
