# Demo Review Report

Taxonomy: `/Users/iamverk/Desktop/HSE/diploma/diploma/../.hidden_eval/exp10_results/taxonomy_final.json`

## Executive Summary

| Check | Result |
|---|---:|
| Agent judge verdict | pilot-ready with targeted review |
| Agent judge score | 3.95 / 5.00 |
| Blocking lint errors | 0 |
| Product assignments needing review | 74.0% |
| Akeneo export files present | yes |

Interpretation: the taxonomy is structurally clean enough for a controlled PIM pilot, but product placement should enter a review queue before unattended import.

## Taxonomy Structure

| Metric | Value |
|---|---:|
| Nodes | 161 |
| Edges | 160 |
| Leaves | 119 |
| Max depth | 4 levels |
| Top-level categories | 10 |
| Mean branching | 3.810 |

### Top-Level Leaf Distribution

| Category | Leaves | Direct children |
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

## Reference-Free Metrics

| Metric | Value |
|---|---:|
| CES mean | 0.5989 |
| CES minimum | 0.3620 |
| Weak edges | 0 |
| CSC | 0.4588 |
| RLPC | 0.7452 |
| LLM judge mean | 4.74 / 5.00 |
| LLM judge valid paths | 96.0% |
| RFTQ-J reconstructed | 0.6911 |

## Linter and Quality Flags

| Severity | Count |
|---|---:|
| error | 0 |
| warn | 12 |
| info | 2 |

Top deterministic flags:

- `redundant_prefix`: Automotive Products -> Automotive Wheels and Tires
- `redundant_prefix`: Vehicle Electronics -> Vehicle Navigation Electronics
- `redundant_prefix`: Women's Clothing -> Women Tops
- `redundant_prefix`: Skin Care -> Skin Serums
- `redundant_prefix`: Home Goods -> Home Decor
- `redundant_prefix`: Home Decor -> Home Rugs
- `redundant_prefix`: Outdoor Goods -> Outdoor Recreation
- `redundant_prefix`: Outdoor Recreation -> Outdoor Cycling
- `redundant_prefix`: Outdoor Recreation -> Outdoor Team Sports
- `redundant_prefix`: Pet Products -> Pet Accessories

## Product-to-Leaf Assignment

| Metric | Value |
|---|---:|
| Products assigned | 150 |
| Leaf coverage in sample | 53.8% |
| Product coverage above threshold | 54.0% |
| Mean assignment score | 0.3656 |
| Ambiguity rate | 63.3% |
| Needs-review rate | 74.0% |

### Confident Assignment Examples

| Product | Assigned leaf | Score |
|---|---|---:|
| FURTIME Dog Bed Crate Pad Ultra Soft Washable Kennel Bed 24/30/36/42 Inch Anti-Slip C... | Pet Beds | 0.628 |
| Mohawk Home Laguna Boardwalk Stripe Area Rug, 5'x8', Blue/Grey | Home Rugs | 0.554 |
| PetSafe Analog 2 Meal Programmable Pet Feeder, Automatic Dog and Cat Feeder - Dry or ... | Wet Food | 0.543 |
| 2LUV Women's Stretchy 5 Pocket Skinny Color Uniform Pants Back to School Junior Cloth... | Jeans | 0.535 |
| FZYTMY Funny Doormat Guns Make Me Happy You Not So Much Indoor Outdoor Entrance Floor... | Home Rugs | 0.532 |

### Review Queue Examples

| Product | Proposed leaf | Score | Reason |
|---|---|---:|---|
| Pregnancy Test Early, Docalon 5 Count Clear and Accurate Results Over 99% Accurate HC... | Early Readers | 0.107 | low_confidence\|ambiguous_top2 |
| Skald Thermogenic Fat Burner for Men and Women - Oxydynamic Fat Scorcher for Weight L... | Moisturizers | 0.196 | low_confidence\|ambiguous_top2 |
| AIRSCALE Digital Bathroom Weight Scale for People, Battery-Free Updated U-Power Techn... | Activewear | 0.207 | low_confidence\|ambiguous_top2 |
| Samsung Printer Xpress M3065FW Laser All-in-One | Laptops | 0.221 | low_confidence\|ambiguous_top2 |
| YILINM 50Feet Outdoor String Lights G40 Globe Patio Lights with 25 Shatterproof Bulbs... | Tents | 0.225 | low_confidence\|ambiguous_top2 |

## Agent Judge

| Criterion | Score |
|---|---:|
| Global structure and navigability | 5.00 / 5.00 |
| Naming specificity and category actionability | 4.69 / 5.00 |
| Product placement readiness | 2.92 / 5.00 |
| Governance and audit readiness | 4.29 / 5.00 |

## Akeneo Export Readiness

| Artifact | Present | Rows/bytes |
|---|---:|---:|
| `akeneo_categories.csv` | yes | 161 |
| `akeneo_categories.xlsx` | yes | 12484 |
| `akeneo_rest_payload.json` | yes | 161 |

## Artifact Inventory

- `assignment_metrics.json`: product-placement summary
- `product_assignments.csv`: product-to-leaf assignments and review flags
- `agent_judge_exp10.json`: deterministic readiness judge output
- `akeneo_categories.csv`, `akeneo_categories.xlsx`, `akeneo_rest_payload.json`: export payloads
- `report.html`: browser-readable version of this report

## Decision

Proceed with a controlled pilot import after category-manager review of low-confidence assignments and flagged naming issues. Do not run unattended bulk product categorization yet.
