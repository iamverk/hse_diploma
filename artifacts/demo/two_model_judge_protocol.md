# Two-Model Judge Protocol: Experiment 10

This protocol records a second model-style audit of the same 50 sampled root-to-leaf paths previously rated by Claude Opus 4.7.

## Scope

- Taxonomy: `/Users/iamverk/Desktop/HSE/diploma/.hidden_eval/exp10_results/taxonomy_final.json`
- Path sample: `/Users/iamverk/Desktop/HSE/diploma/.hidden_eval/exp10_results/judge_paths.json`
- First judge: Claude Opus 4.7, stored in `.hidden_eval/exp10_results/judge_ratings.json`
- Second judge: Codex agent environment, stored in `artifacts/demo/codex_judge_ratings.json`
- Rubric: 1 = invalid IS-A, 2 = major parent-child error, 3 = product-taxonomy issue or activity/category mismatch, 4 = minor naming/scope flaw, 5 = clean product-category path.

This is not a human evaluation and not a full cross-model reliability study. It is a protocol-level second-model audit for the deployment candidate taxonomy.

## Summary

| Judge | Mean | Median | Valid paths >= 4 | Invalid paths <= 2 | Distribution |
|---|---:|---:|---:|---:|---|
| Claude Opus 4.7 | 4.74 | 5 | 96.0% | 4.0% | 2: 2, 4: 8, 5: 40 |
| Codex agent | 4.66 | 5 | 94.0% | 4.0% | 2: 2, 3: 1, 4: 9, 5: 38 |

Agreement:

- Exact rating agreement: 46 / 50 paths, or 92.0%.
- Both judges flag the same two major invalid paths: `Products > Electronics > Smartphones > Phone Cases` and `Products > Electronics > Cameras > Lenses`.
- Codex is stricter on four paths: `Batteries`, `Dice Games`, `Adventure Sports`, and `Figurines`.
- Codex is not more lenient on any path.

## Interpretation

The second-model audit supports the main qualitative conclusion for Experiment 10: the taxonomy is strong enough for a controlled PIM pilot, but it still contains a small number of category-actionability issues.

The strongest agreement is on major errors. Both judges independently identify accessory/component placement issues for `Phone Cases` under `Smartphones` and `Lenses` under `Cameras`. The disagreements are one-point strictness differences, mostly around activity labels or scope boundaries rather than hard graph invalidity.

The protocol therefore reduces, but does not eliminate, the self-judging concern. Broader cross-model judging across Naive, CoL-light, and multiple Ralph experiments remains future work.

## Recommended Text for Thesis

An additional post-draft protocol audit was performed on the 50 Experiment 10 judge paths using Codex agent as a second model-style reviewer. Codex produced a mean path rating of 4.66 out of 5, compared with 4.74 for Claude Opus 4.7, with 92.0% exact agreement. Both judges identified the same two major invalid paths. This audit is not a replacement for human evaluation, but it provides a second-model sanity check for the production-candidate taxonomy. GPT-4o-mini was not used for this protocol.
