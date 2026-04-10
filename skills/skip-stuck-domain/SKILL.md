---
name: skip-stuck-domain
description: |
  Detect and skip domains stuck in rollback loops (3+ consecutive discards).
  Invoked automatically when rollback-counter hook detects a stuck domain,
  or manually when repeated attempts on the same domain keep failing.
---

# Skip Stuck Domain

## When to use
- The rollback-counter hook reports 3+ consecutive rollbacks on the same domain
- You've tried multiple approaches on a domain and CSC keeps regressing
- The `output/stuck_domains.txt` file lists the current domain

## Why domains get stuck
The CSC metric uses Wu-Palmer similarity from WordNet. Domains whose terminology
has poor WordNet coverage get artificially low CSC scores regardless of taxonomy quality:
- **Pet Products**: "Dry Food", "Wet Food", "Pet Toys" — poor WordNet synsets
- **Cosmetics**: "BB Cream", "Setting Spray" — not in WordNet
- **Auto Parts**: "Brake Pads", "Oil Filters" — limited coverage

This is a **metric artifact**, not an agent failure. The taxonomy may be structurally correct
but CSC can't measure it.

## Action steps

1. **Check stuck_domains.txt**:
   ```bash
   cat output/stuck_domains.txt
   ```

2. **Log the skip** in progress.txt (Discovered Patterns section):
   ```
   - Domain [X] skipped after N rollbacks — Wu-Palmer CSC ceiling for this domain
   ```

3. **Mark current story as passes: true** in prd.json with a note:
   ```
   "notes": "skipped — CSC metric ceiling, N consecutive rollbacks"
   ```

4. **Do NOT retry** this domain. Move to the next story.

5. **Commit**:
   ```bash
   git add -A && git commit -m "story N: skip [domain] — CSC metric ceiling"
   ```

6. Output `<promise>COMPLETE</promise>`

## Important
- This is NOT a failure — it's an informed decision to stop burning iterations
- Document the skip clearly for experiment analysis
- The domain can be revisited in a future experiment with a different CSC metric
