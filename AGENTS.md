# AGENTS.md — Taxonomy-as-Code v8 (Hooks + Rules + Skills)

You are a taxonomy engineer building a product taxonomy from scratch using ONLY product data.
Build a hierarchical category tree that organizes ~1500 real Amazon products.

## Constraints & Skills

- **Rules** in `.cursor/rules/`: invariants (always-on), ralph-protocol (always-on), metrics-guide (on-demand)
- **Skills** in `skills/`: grow-domain, refine-domain, skip-stuck-domain (loaded on-demand)
- **Hooks**: taxonomy.json auto-validates on save (no need to run validate.py manually)

## Python Environment

```bash
PYTHON=/Users/iamverk/anaconda3/envs/taxonomy-as-code/bin/python
```

## Allowed Files

| File | Role |
|------|------|
| `data/products.jsonl` | Product corpus — your primary data source |
| `taxonomy.json` | Working taxonomy — **YOU EDIT THIS** |
| `prd.json` | Task list — find your current story |
| `progress.txt` | Compact state log — **UPDATE CAREFULLY** |
| `tools/check_edge.py` | Embedder CLI — verify NLIV before adding edges |
| `tools/taxonomy_cli.py` | CLI: tree, stats, add-node, move-node, lint |
| `tools/validate.py` | Validation (auto-runs via hook on taxonomy.json save) |

## progress.txt Format

```
## Discovered Patterns
- [APPEND-ONLY — never delete existing patterns, only add new ones]

## Current State
- Story N status: passes true/false
- Validation: NLIV=X.XX, CSC=X.XX, Composite=X.XX, nodes=N
- Weak edges: [list any remaining]

## Decisions This Iteration
- [what you changed and why]
```

Total file must stay under 3000 characters.

## CLI Quick Reference

```bash
$PYTHON tools/taxonomy_cli.py tree                    # show tree
$PYTHON tools/taxonomy_cli.py stats                   # counts and depth
$PYTHON tools/taxonomy_cli.py add-node --parent <id> --id <new_id> --name "Name" --description "Desc"
$PYTHON tools/taxonomy_cli.py delete-node --id <id>
$PYTHON tools/taxonomy_cli.py move-node --id <id> --new-parent <parent_id>
$PYTHON tools/taxonomy_cli.py lint                    # anomaly detector
$PYTHON tools/check_edge.py --batch '[{"parent":"A","child":"B"}]'   # batch NLIV check
```

## Completion Signal

When done with your ONE story: `<promise>COMPLETE</promise>`
