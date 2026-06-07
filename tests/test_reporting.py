from argparse import Namespace

from tools.reporting import build_report_data, parse_metrics_text, render_markdown_report
from tools.taxonomy_core import save_taxonomy


def test_parse_metrics_text(tmp_path):
    metrics = tmp_path / "metrics.txt"
    metrics.write_text(
        """
Nodes: 161  Edges: 160  Leaves: 119  Max depth: 3
  Mean:  0.5989
  Min:   0.3620
  Weak edges (CES < 0.3): 0
  Score:   0.4588
  p-value: 0.0000
  Pairs:   200
  Chains:      0
  Branching:   mean=3.8  std=1.7  CV=0.44
  Leaf ratio:  0.74
RFTQ-D SCORE: 0.6510
""",
        encoding="utf-8",
    )

    parsed = parse_metrics_text(metrics)

    assert parsed["node_count"] == 161
    assert parsed["ces_mean"] == 0.5989
    assert parsed["weak_edges_count"] == 0


def test_build_report_data_and_markdown(tmp_path):
    taxonomy = {
        "id": "products",
        "name": "Products",
        "children": [
            {"id": "books", "name": "Books", "children": [{"id": "fiction", "name": "Fiction Books"}]},
            {"id": "home", "name": "Home Goods", "children": [{"id": "candles", "name": "Decorative Candles"}]},
        ],
    }
    taxonomy_path = tmp_path / "taxonomy.json"
    save_taxonomy(taxonomy, taxonomy_path)

    metrics_text = tmp_path / "metrics.txt"
    metrics_text.write_text(
        """
Nodes: 5  Edges: 4  Leaves: 2  Max depth: 2
  Mean:  0.6000
  Min:   0.4000
  Weak edges (CES < 0.3): 0
  Score:   0.5000
  p-value: 0.0100
  Pairs:   10
  Chains:      0
  Branching:   mean=2.0  std=0.0  CV=0.00
  Leaf ratio:  0.40
RFTQ-D SCORE: 0.6500
""",
        encoding="utf-8",
    )
    rlpc = tmp_path / "rlpc.json"
    rlpc.write_text('{"rlpc_score": 0.75, "mono_mean_score": 0.9, "step_mean": 0.6, "path_nli_mean": 0.8}', encoding="utf-8")
    judge = tmp_path / "judge.json"
    judge.write_text('{"summary": {"mean": 4.5, "pct_valid_ge4": 0.9}, "ratings": []}', encoding="utf-8")
    assignment_metrics = tmp_path / "assignment_metrics.json"
    assignment_metrics.write_text('{"product_count": 1, "coverage": 1.0, "leaf_coverage": 0.5, "needs_review_rate": 0.0}', encoding="utf-8")
    assignments = tmp_path / "assignments.csv"
    assignments.write_text(
        "product_id,title,assigned_leaf_name,score,needs_review,review_reason\n"
        "p1,Scented candle,Decorative Candles,0.72,false,\n",
        encoding="utf-8",
    )
    agent = tmp_path / "agent.json"
    agent.write_text(
        '{"overall_score_1_5": 4.0, "verdict": "pilot-ready", "criteria": [], '
        '"redundant_edge_examples": [], "low_information_leaf_examples": []}',
        encoding="utf-8",
    )
    (tmp_path / "akeneo_categories.csv").write_text("code;parent;label-en_US\nproducts;;Products\n", encoding="utf-8")
    (tmp_path / "akeneo_rest_payload.json").write_text('[{"code": "products"}]', encoding="utf-8")
    (tmp_path / "akeneo_categories.xlsx").write_bytes(b"xlsx")

    args = Namespace(
        taxonomy=str(taxonomy_path),
        metrics_text=str(metrics_text),
        rlpc_json=str(rlpc),
        judge_ratings=str(judge),
        assignment_metrics=str(assignment_metrics),
        assignments=str(assignments),
        agent_judge=str(agent),
        lint_report=None,
        artifact_dir=str(tmp_path),
    )

    data = build_report_data(args)
    markdown = render_markdown_report(data)

    assert data["taxonomy_stats"]["nodes"] == 5
    assert "Taxonomy Review Report" in markdown
    assert "Akeneo Export Readiness" in markdown
