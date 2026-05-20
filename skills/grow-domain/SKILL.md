---
name: grow-domain
description: |
  Expand a taxonomy domain by sampling products and adding L2/L3 categories.
  Use during Phase 1 (growth) stories when the goal is adding nodes.
---

# Grow Domain

## When to use
- Stories that say "Expand", "Add L2/L3", or target a node count
- Phase 1 stories in the PRD

## Workflow: grep → check → add → validate

### 1. Sample products
```bash
grep -i "keyword" data/products.jsonl | head -50
```
Sample 50–100 products from the target domain. Use product titles to discover real category names.

### 2. Batch-check edges (ALWAYS use --batch)
```bash
$PYTHON tools/check_edge.py --batch '[
  {"parent":"Electronics","child":"Cameras"},
  {"parent":"Electronics","child":"Headphones"}
]'
```
Model loads once, checks all edges instantly. Single checks load model each time (~30s!).

### 3. Add nodes
```bash
$PYTHON tools/taxonomy_cli.py add-node \
  --parent <parent_id> --id <new_id> \
  --name "Human Name" --description "Description"
```
Or edit taxonomy.json directly (faster for bulk adds).

### 4. Auto-validation
The `afterFileEdit` hook runs validate.py automatically on taxonomy.json save.
Read the followup_message for NLIV/CSC/Composite metrics.

### 5. Fix and iterate
- If WEAK/BAD edges → rename child or choose different parent
- If chains → add siblings
- If NLIV too low → add intermediate category

## Naming conventions
- Function-based, not brand-based: "Audio Equipment" not "Sony Products"
- Use product titles as signals: "Wireless Bluetooth Headphones" → Audio > Headphones
- Concrete domain names: "Camping Gear" not "Outdoor Stuff"
- Electronics L3: capability/form-factor (Gaming, Premium, 5G)
- Clothing L3: context-based splits (casual, athletic, formal, seasonal)

## Target per story
- 10–20 new nodes per story (atomic sizing)
- Keep NLIV > 0.40 while growing
- Zero chains after each story
