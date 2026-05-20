# Defense Demo Script

Цель демо: показать, что результат ВКР - это не только JSON-таксономия, а воспроизводимый productization pipeline: метрики, review queue, независимая проверка и PIM-ready export.

## Перед показом

Запустить или показать команду:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,pim]"
make demo
```

Открывать файлы лучше в таком порядке.

| Шаг | Файл | Что сказать |
|---:|---|---|
| 1 | `artifacts/demo/report.html` | "This is the consolidated business-facing report. It combines the taxonomy structure, reference-free metrics, review queue, agent judge, and Akeneo export status." |
| 2 | `artifacts/demo/report.html`, Executive Summary | "The production candidate has 161 nodes, 119 leaves, zero blocking lint errors, and reconstructed RFTQ-J = 0.6911." |
| 3 | `artifacts/demo/product_assignments.csv` | "Products are assigned to leaf categories with top-3 alternatives. Low-confidence and ambiguous cases are not silently imported; they are sent to review." |
| 4 | `artifacts/demo/agent_judge_exp10.md` | "I added a deterministic agent-style judge as an extra global reviewer. It gives 3.95 out of 5 and the verdict: pilot-ready with targeted review." |
| 5 | `artifacts/demo/two_model_judge_protocol.md` | "For the protocol, the same 50 paths were evaluated by Claude Opus 4.7 and by Codex. Exact agreement is 92%, and both judges flag the same two major invalid paths." |
| 6 | `artifacts/demo/akeneo_categories.csv` or `akeneo_rest_payload.json` | "The same taxonomy is exported into Akeneo-compatible category records: code, parent, and labels. This is the handoff from research artifact to PIM artifact." |

## Ключевые цифры

| Metric | Value | Meaning |
|---|---:|---|
| Nodes / leaves | 161 / 119 | Size of the deployable taxonomy |
| Max depth | 4 levels | Navigable hierarchy, not a flat list |
| Blocking lint errors | 0 | Passes the production-candidate gate |
| Weak edges | 0 | No parent-child edge below the CES threshold |
| RFTQ-J | 0.6911 | Reference-free quality score with Judge component |
| Agent judge score | 3.95 / 5.00 | Independent readiness check |
| Two-model judge agreement | 92.0% | Claude Opus 4.7 and Codex on the same 50 paths |
| Assignments needing review | 74.0% | Automatic placement should start as a review queue |
| Akeneo export rows | 161 | One category record per taxonomy node |

## Короткий рассказ на 60-90 секунд

"The main contribution is a blind taxonomy construction pipeline. It does not require a gold-standard taxonomy: the system builds a hierarchy, evaluates it with reference-free metrics, rolls back regressions, and then applies a production-candidate gate.

For the productization step, I selected Ralph Experiment 10 because it is the only run with zero blocking lint errors. It is not the highest by the research RFTQ-J score, but it is the best deployment candidate. The final taxonomy has 161 nodes, 119 leaves, 10 top-level categories, and no weak edges.

The demo command `make demo` regenerates the practical artifacts. The report summarizes the metrics and decision. The assignment CSV shows how products are mapped to leaves and which items require review. The agent judge adds an independent deterministic readiness assessment. I also added a second model-style protocol check: Claude Opus 4.7 and Codex agree exactly on 92% of the same 50 path ratings and flag the same two major invalid paths. Finally, the exporter generates CSV, XLSX, and JSON payloads compatible with Akeneo category import patterns.

So the practical result is not unattended automatic categorization. It is a controlled PIM pilot: structurally clean taxonomy, auditable metrics, explicit review queue, and export-ready files."

## Не говорить лишнего

- Не говорить: "I imported it into a live Akeneo instance."
- Говорить: "The payload matches the Akeneo category schema; live import requires credentials and a configured PIM instance."
- Не говорить: "The system categorizes products fully automatically."
- Говорить: "The system creates a review queue and makes uncertainty explicit."
- Не говорить: "Experiment 10 is the best taxonomy by every metric."
- Говорить: "Experiment 10 is the best production candidate because it passes the zero-error gate."
- Не говорить: "This is human inter-rater reliability."
- Говорить: "This is a second model-style protocol audit; human evaluation remains future work."

## Если спросят

**Why is the review rate 74%?**  
Because the assignment threshold is conservative and the product sample is noisy and broader than some taxonomy leaves. This is intentional: uncertain placements are surfaced for category-manager review rather than silently imported.

**Why not use Experiment 7 if it has the best RFTQ-J?**  
Experiment 7 is strongest by the research metric, but it has a blocking linter error. Experiment 10 has a slightly lower RFTQ-J score but passes the production-candidate gate with zero errors.

**What exactly is reproducible?**  
The command `make demo` regenerates product assignments, assignment metrics, agent judge reports, Akeneo CSV/XLSX/JSON exports, and the unified HTML/Markdown report.

**What does the second judge add?**  
It reduces the self-judge concern for the deployment candidate: Claude Opus 4.7 and Codex agree exactly on 46 of 50 path ratings and identify the same two major invalid paths. It does not replace human evaluation.

**What remains future work?**  
Live import into a configured Akeneo instance, larger assignment benchmark, downstream A/B tests, and migration scripts for taxonomy versioning.
