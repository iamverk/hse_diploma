# Cross-Embedder Probe

Post-hoc robustness check for CES and CSC on the key thesis taxonomies. The construction loop used `all-MiniLM-L6-v2`; this artifact recomputes CES and CSC with `all-MiniLM-L6-v2`, `all-mpnet-base-v2`, and `bge-base-en-v1.5` from the local HuggingFace cache. It is not used for rollback or weight selection.

## all-MiniLM-L6-v2

| Method | Nodes | CES mean | CSC | Weak edges < 0.3 |
|---|---:|---:|---:|---:|
| Ralph Exp. 7 | 211 | 0.620 | 0.491 | 0 |
| Ralph Exp. 10 | 161 | 0.599 | 0.459 | 0 |
| CoL-light | 239 | 0.530 | 0.258 | 16 |
| Naive | 265 | 0.536 | 0.236 | 19 |

CES ranking: Ralph Exp. 7 > Ralph Exp. 10 > Naive > CoL-light

CSC ranking: Ralph Exp. 7 > Ralph Exp. 10 > CoL-light > Naive

## all-mpnet-base-v2

| Method | Nodes | CES mean | CSC | Weak edges < 0.3 |
|---|---:|---:|---:|---:|
| Ralph Exp. 7 | 211 | 0.629 | 0.522 | 1 |
| Ralph Exp. 10 | 161 | 0.612 | 0.464 | 0 |
| CoL-light | 239 | 0.551 | 0.256 | 12 |
| Naive | 265 | 0.563 | 0.205 | 12 |

CES ranking: Ralph Exp. 7 > Ralph Exp. 10 > Naive > CoL-light

CSC ranking: Ralph Exp. 7 > Ralph Exp. 10 > CoL-light > Naive

## bge-base-en-v1.5

| Method | Nodes | CES mean | CSC | Weak edges < 0.3 |
|---|---:|---:|---:|---:|
| Ralph Exp. 7 | 211 | 0.764 | 0.529 | 0 |
| Ralph Exp. 10 | 161 | 0.751 | 0.465 | 0 |
| CoL-light | 239 | 0.727 | 0.274 | 0 |
| Naive | 265 | 0.734 | 0.220 | 0 |

CES ranking: Ralph Exp. 7 > Ralph Exp. 10 > Naive > CoL-light

CSC ranking: Ralph Exp. 7 > Ralph Exp. 10 > CoL-light > Naive

## Interpretation

Across the independent `all-mpnet-base-v2` and `bge-base-en-v1.5` checks, the Ralph taxonomies remain above the Naive and CoL-light baselines on CSC. Exp. 7 stays the strongest CSC result under all three embedders. CES is more sensitive to lexical naming and threshold scale: weak-edge counts change under `all-mpnet-base-v2` and `bge-base-en-v1.5`, but Exp. 7 and Exp. 10 remain above the baselines by CES. The result supports the structural-coherence claim most strongly and should be read as a post-hoc robustness probe, not as a full cross-embedder experimental design.
