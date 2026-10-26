"""Render an offline fixture example through the existing plotting function.

Uses the test suite's SQLite adapter and document-list double. No MySQL,
MongoDB or Neo4j service is contacted; this is not an integration benchmark.
"""
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from unittest.mock import patch

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import load_data
import visualisations

ROOT = Path(__file__).resolve().parent


def main():
    spec = spec_from_file_location("local_fixture", ROOT / "tests" / "test_loading_and_graphs.py")
    fixtures = module_from_spec(spec)
    spec.loader.exec_module(fixtures)
    sql, documents = fixtures.SQLFixture(), fixtures.MongoFixture()
    try:
        for category in ("books", "sports"):
            load_data.load_dataset(sql, documents, ROOT / "data" / f"synthetic_{category}.jsonl",
                                   f"demo_{category}")

        def query_rows(statement, parameters=()):
            return sql.db.execute(statement.replace("%s", "?"), parameters).fetchall()

        with patch.object(visualisations, "query_rows", side_effect=query_rows), \
                patch.object(visualisations, "choose_category", return_value=None), \
                patch("builtins.input", return_value="1"), \
                patch.object(plt, "show"):
            visualisations.rating_histogram()
        figure = plt.gcf()
        figure.axes[0].set_title("Synthetic fixture: ratings across both categories")
        figure.text(0.5, 0.015, "12 fictitious review events; 11 ratings, 1 missing. SQLite + document-list double.",
                    ha="center", fontsize=9, color="#475569")
        figure.tight_layout(rect=(0, 0.045, 1, 1))
        output = ROOT / "docs" / "images"
        output.mkdir(parents=True, exist_ok=True)
        figure.savefig(output / "synthetic-ratings.png", dpi=160, metadata={"Software": "Matplotlib"})
        summary = {
            "scope": "Synthetic fixture only; SQLite and document-list double, no external services",
            "users": sql.db.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0],
            "items": sql.db.execute("SELECT COUNT(*) FROM articulos").fetchone()[0],
            "review_events": sql.db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0],
            "non_null_ratings": sql.db.execute("SELECT COUNT(overall) FROM reviews").fetchone()[0],
            "document_double_count": len(documents.documents),
        }
        print(json.dumps(summary, indent=2))
    finally:
        sql.close()
        plt.close("all")


if __name__ == "__main__":
    main()
