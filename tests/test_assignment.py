from tools.assignment import assign_products, collect_leaves, normalize_text, read_products


def test_collect_leaves_and_paths():
    taxonomy = {
        "id": "products",
        "name": "Products",
        "children": [
            {
                "id": "books",
                "name": "Books",
                "children": [
                    {"id": "fiction", "name": "Fiction", "description": "Novels and stories"},
                ],
            },
            {"id": "tools", "name": "Tools", "description": "Hand tools"},
        ],
    }

    leaves = collect_leaves(taxonomy)

    assert [leaf.id for leaf in leaves] == ["fiction", "tools"]
    assert leaves[0].path == "Products > Books > Fiction"
    assert leaves[0].top_level_id == "books"


def test_assignment_lexical_backend_selects_relevant_leaf():
    taxonomy = {
        "id": "products",
        "name": "Products",
        "children": [
            {"id": "books", "name": "Books", "description": "Books and novels"},
            {"id": "candles", "name": "Candles", "description": "Scented soy candles and home fragrance"},
        ],
    }
    products = [
        {
            "product_id": "p1",
            "title": "Vanilla scented soy candle",
            "description": "Home fragrance candle gift",
            "assignment_text": "Vanilla scented soy candle. Home fragrance candle gift",
        }
    ]

    rows, summary = assign_products(products, collect_leaves(taxonomy), backend="lexical")

    assert rows[0]["assigned_leaf_id"] == "candles"
    assert summary["product_count"] == 1
    assert summary["backend"] == "lexical"


def test_read_products_normalizes_html(tmp_path):
    path = tmp_path / "products.jsonl"
    path.write_text(
        '{"product_id":"1","name":"<b>Book</b>","description":"A&nbsp;novel"}\n',
        encoding="utf-8",
    )

    products = read_products(path)

    assert products[0]["title"] == "Book"
    assert products[0]["description"] == "A novel"
    assert normalize_text("<p>x&nbsp;y</p>") == "x y"
