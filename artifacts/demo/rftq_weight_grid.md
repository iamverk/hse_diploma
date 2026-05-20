# RFTQ-J Weight Grid Robustness Check

This artifact evaluates whether the reported RFTQ-J ranking depends on a single hand-picked weight vector. It is a robustness grid, not a procedure for choosing the final weights.

Grid definition: five component weights (CES, CSC, RLPC, Judge, Struct), step 0.05, each weight constrained to [0.05, 0.50], with total weight 1.00. This yields 3246 plausible weight vectors. The grid uses the retained method-level table with complete component values used by the thesis sensitivity analysis.

## Top Method Frequency

| Top method | Grid points | Share |
|---|---:|---:|
| Exp. 7 | 3231 | 99.5% |
| Exp. 9 | 15 | 0.5% |

## Mean Rank and Top-3 Share

| Method | Mean rank | Top-3 share |
|---|---:|---:|
| Exp. 7 | 1.005 | 100.0% |
| Exp. 8 | 2.594 | 95.7% |
| Exp. 10 | 2.971 | 69.1% |
| Exp. 5 | 3.908 | 22.3% |
| Exp. 9 | 5.143 | 12.8% |
| Exp. 1 | 6.394 | 0.0% |
| Exp. 6 | 6.65 | 0.0% |
| Naive | 7.335 | 0.0% |

Interpretation: Exp. 7 is the top method in 99.5% of plausible grid points and has the best mean rank. This supports the narrower claim that the ranking is not an artifact of the exact default weights. It does not remove the cross-embedder or Goodhart limitations because several components share the same embedding space and RFTQ-J is still used as both an objective and a reported metric.
