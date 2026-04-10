---
name: refine-domain
description: |
  Fix weak edges, balance structure, and optimize quality metrics in existing taxonomy.
  Use during Phase 2 (refinement) stories when the goal is improving NLIV/CSC/Composite.
---

# Refine Domain

## When to use
- Stories that say "Fix", "Refine", "Optimize", or "MECE audit"
- Phase 2 stories in the PRD
- When composite is plateauing and weak edges remain

## Strategy: fix worst first

### 1. Identify weak edges
```bash
$PYTHON tools/validate.py
```
Read the `weak_edges` list — these are edges with NLIV < 0.3.

### 2. Fix strategies (priority order)

**Rename child** — most common fix:
- "Cables" → "Audio Cables" (more specific IS-A)
- "Recipes" → "Recipe Books" (disambiguate from parent)

**Add intermediate category** — when IS-A is too loose:
- Before: Electronics → Cables (NLIV=0.22)
- After: Electronics → Accessories → Cables (NLIV=0.45)

**Move node** — when it's under wrong parent:
```bash
$PYTHON tools/taxonomy_cli.py move-node --id <node_id> --new-parent <new_parent_id>
```

**Merge nodes** — when two siblings overlap (MECE violation):
- Delete one, rename the other to cover both

### 3. MECE audit
For each non-leaf node, check:
- **Exclusive**: no product should fit in two sibling categories
- **Exhaustive**: every product in parent's domain fits some child
- Test with: `grep -i "domain" data/products.jsonl | head -30`

### 4. Structural balance
```bash
$PYTHON tools/taxonomy_cli.py lint
```
- Fix chains (single-child nodes): add siblings or merge with parent
- Fix high branching (>15 children): create sub-groups
- Target branching CV < 0.8

## Targets
- NLIV > 0.50, zero edges < 0.25
- CSC > 0.35
- Composite > 0.60
- Zero chains, branching CV < 0.8
