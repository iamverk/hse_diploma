from tools.agent_judge import build_agent_judge_report


def test_agent_judge_scores_taxonomy_with_assignment_metrics():
    taxonomy = {
        "id": "root",
        "name": "Products",
        "children": [
            {
                "id": "home",
                "name": "Home Goods",
                "children": [
                    {
                        "id": "decor",
                        "name": "Home Decor",
                        "children": [
                            {"id": "candles", "name": "Decorative Candles"},
                            {"id": "vases", "name": "Decorative Vases"},
                        ],
                    }
                ],
            },
            {
                "id": "electronics",
                "name": "Electronics",
                "children": [
                    {
                        "id": "audio",
                        "name": "Audio",
                        "children": [
                            {"id": "headphones", "name": "Headphones"},
                            {"id": "speakers", "name": "Speakers"},
                        ],
                    }
                ],
            },
        ],
    }
    metrics = {
        "coverage": 0.75,
        "leaf_coverage": 0.80,
        "needs_review_rate": 0.20,
        "mean_assignment_score": 0.45,
    }

    report = build_agent_judge_report(taxonomy, assignment_metrics=metrics)

    assert report["overall_score_1_5"] > 3.0
    assert report["statistics"]["leaves"] == 4
    assert any(c["name"] == "Product placement readiness" for c in report["criteria"])


def test_agent_judge_flags_low_information_leaf():
    taxonomy = {
        "id": "root",
        "name": "Products",
        "children": [
            {
                "id": "misc",
                "name": "Miscellaneous",
                "children": [
                    {"id": "items", "name": "Items"},
                ],
            }
        ],
    }

    report = build_agent_judge_report(taxonomy)

    assert report["low_information_leaf_examples"]
    assert report["flagged_paths"]
