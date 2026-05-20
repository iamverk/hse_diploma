# Agent Judge Report

Taxonomy: `/Users/iamverk/Desktop/HSE/diploma/diploma/../.hidden_eval/exp10_results/taxonomy_final.json`

Overall score: **3.95 / 5.00** (0.790 normalized)

Verdict: **pilot-ready with targeted review**

## Criteria

| Criterion | Weight | Score | Evidence | Main risks |
|---|---:|---:|---|---|
| Global structure and navigability | 0.30 | 5.00 | 161 nodes, 119 leaves, 4 levels<br>10 top-level categories<br>single-child internal ratio: 0.0%<br>top-level leaf imbalance CV: 0.35 | No major risk detected. |
| Naming specificity and category actionability | 0.25 | 4.69 | 2 low-information leaf labels<br>21 redundant parent-child prefixes<br>0 duplicate normalized labels<br>0 labels longer than six tokens | Some leaves are too generic to support confident product assignment.<br>Some child labels repeat the parent concept instead of adding specificity. |
| Product placement readiness | 0.25 | 2.92 | product coverage above threshold: 54.0%<br>leaf coverage in sample: 53.8%<br>assignments needing review: 74.0%<br>mean assignment score: 0.366 | High review rate: product placement is not yet reliable enough for unattended import.<br>Less than 60% of sampled products exceed the confidence threshold. |
| Governance and audit readiness | 0.20 | 4.29 | valid DAG: True<br>root count: 1<br>auditable top-level distribution is available<br>agent judge is deterministic and reproducible | A high product-placement review rate should be handled before unattended PIM import. |

## Structure Summary

- Nodes: 161
- Leaves: 119
- Max depth: 4 levels
- Top-level categories: 10
- Single-child internal nodes: 0

## Top-Level Leaf Distribution

| Top-level category | Leaves | Direct children |
|---|---:|---:|
| Books | 18 | 7 |
| Home Goods | 18 | 3 |
| Clothing | 15 | 5 |
| Electronics | 15 | 5 |
| Toys | 12 | 2 |
| Automotive Products | 9 | 3 |
| Pet Products | 9 | 3 |
| Tools | 9 | 3 |
| Outdoor Goods | 8 | 2 |
| Cosmetics | 6 | 2 |

## Flagged Path Examples

- `Products > Automotive Products > Automotive Wheels and Tires > Rims`: redundant_prefix
- `Products > Automotive Products > Automotive Wheels and Tires > Tires`: redundant_prefix
- `Products > Automotive Products > Automotive Wheels and Tires > Wheel Brakes`: redundant_prefix
- `Products > Automotive Products > Vehicle Electronics > Vehicle Navigation Electronics`: redundant_prefix
- `Products > Clothing > Women's Clothing > Women Tops`: redundant_prefix
- `Products > Cosmetics > Skin Care > Skin Serums`: redundant_prefix
- `Products > Home Goods > Home Decor > Decorative Home Candles`: redundant_prefix
- `Products > Home Goods > Home Decor > Decorative Lighting`: redundant_prefix
- `Products > Home Goods > Home Decor > Decorative Vases`: redundant_prefix
- `Products > Home Goods > Home Decor > Home Rugs`: redundant_prefix
