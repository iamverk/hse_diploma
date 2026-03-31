# Taxonomy-as-Code — Claude Code Instructions

You are a taxonomy engineer. Your job is to build and improve a product taxonomy.

## Your Environment
- `taxonomy.json` — the working taxonomy (YOU EDIT THIS)
- `reference/gold_standard.json` — target taxonomy for comparison (DO NOT EDIT)
- `prd.json` — task list; find the first story where `passes: false`
- `progress.txt` — learnings from previous iterations (READ THIS FIRST)
- `AGENTS.md` — detailed rules for taxonomy structure

## Every Iteration
1. Read `progress.txt` to learn from past attempts
2. Read `prd.json` to find your current task
3. Read `taxonomy.json` to see current state
4. Make your changes (edit taxonomy.json directly or use CLI tools)
5. Run: `python tools/validate.py` — MUST pass
6. Run: `python tools/metrics.py taxonomy.json reference/gold_standard.json` — check score
7. If validate passes, update `prd.json` to set your story's `passes: true`
8. Append what you learned to `progress.txt`
9. Commit your changes with a descriptive message

## CLI Tools Available
```bash
python tools/taxonomy_cli.py tree                    # show current tree
python tools/taxonomy_cli.py stats                   # node count, depth, etc.
python tools/taxonomy_cli.py add-node --parent X --id Y --name "Z" --description "..."
python tools/taxonomy_cli.py delete-node --id X
python tools/taxonomy_cli.py move-node --id X --new-parent Y
python tools/taxonomy_cli.py search --query "phone"
python tools/taxonomy_cli.py validate                # structure check
python tools/taxonomy_cli.py metrics -r reference/gold_standard.json
python tools/taxonomy_cli.py lint                    # find anomalies
```

## Rules
- Node IDs: lowercase_snake_case, unique
- Parent must be semantically broader than children
- Siblings must be mutually exclusive
- Max depth: 7, min fanout: 2, max fanout: 15
- Every node needs: id, name, description

## Completion Signal
When your task is done and validate passes, output:
<promise>COMPLETE</promise>
