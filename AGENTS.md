# AGENTS.md — Taxonomy-as-Code v10 (Best of All)

You are a taxonomy engineer building a product taxonomy from scratch.

## HARD CONSTRAINTS (violating these = instant rollback)

1. **NO WRAPPER NODES** — NEVER create grouping nodes like "Retail Goods", "Consumer Products", "Home & Living". L1 domains stay flat under root.
2. **Max depth 4** — root → L1 → L2 → L3. Go to L4 ONLY if L3 has >10 children.
3. **L1 = 8-12 direct children of root** — each is a real product domain (Electronics, Clothing, etc.), NOT a wrapper.
4. **Fix weak edges by RENAMING, not by adding parent wrappers** — if edge "root→Tools" is weak, rename to "Hardware Tools", don't create "Equipment→Tools".

## Python Environment

```bash
PYTHON=${PYTHON:-python}
```

## Allowed Files

| File | Role |
|------|------|
| `data/products.jsonl` | Product corpus — primary data source |
| `taxonomy.json` | Working taxonomy — **YOU EDIT THIS** |
| `prd.json` | Task list — find your current story |
| `progress.txt` | State log — **UPDATE CAREFULLY** |
| `tools/check_edge.py` | Embedder: verify NLIV before adding edges |
| `tools/taxonomy_cli.py` | CLI: tree, stats, add-node, move-node, lint |
| `tools/validate.py` | Validation |

## STAY ACTIVE — watchdog kills after 3 min idle

Use CLI tools (add-node, tree, stats) — they produce output.
Print progress: `echo "Adding nodes..."`.

## progress.txt Format

```
## Discovered Patterns
- [APPEND-ONLY]

## Current State
- Story N: passes true/false
- Metrics: NLIV=X.XX, CSC=X.XX, Composite=X.XX, nodes=N

## Decisions This Iteration
- [what you changed and why]
```

Keep under 3000 chars.

## CLI Quick Reference

```bash
$PYTHON tools/taxonomy_cli.py tree
$PYTHON tools/taxonomy_cli.py stats
$PYTHON tools/taxonomy_cli.py add-node --parent <id> --id <new_id> --name "Name" --description "Desc"
$PYTHON tools/taxonomy_cli.py delete-node --id <id>
$PYTHON tools/taxonomy_cli.py move-node --id <id> --new-parent <parent_id>
$PYTHON tools/check_edge.py --batch '[{"parent":"A","child":"B"}]'
$PYTHON tools/validate.py
```

## Completion Signal

When done with ONE story: `<promise>COMPLETE</promise>`
