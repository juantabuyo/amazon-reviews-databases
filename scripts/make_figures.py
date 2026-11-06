"""Render the project's rating view using its bundled synthetic SQL fixture.

The loader and plotting function are unchanged. SQLite and the existing MongoDB
test double stand in for servers; this is not a live database integration.
"""
import argparse
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from load_data import load_dataset
from test_loading_and_graphs import MongoFixture, SQLFixture
import visualisations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "docs/images/synthetic-rating-distribution.png")
    args = parser.parse_args()
    sql, mongo = SQLFixture(), MongoFixture()

    def query_rows(statement, parameters=()):
        cursor = sql.cursor()
        try:
            cursor.execute(statement, parameters)
            return cursor.fetchall()
        finally:
            cursor.close()

    try:
        for category, filename in (("demo_books", "synthetic_books.jsonl"),
                                   ("demo_sports", "synthetic_sports.jsonl")):
            load_dataset(sql, mongo, ROOT / "data" / filename, category)
        with patch.object(visualisations, "query_rows", side_effect=query_rows), \
                patch.object(visualisations, "choose_category", return_value=None), \
                patch("builtins.input", return_value="1"), patch.object(plt, "show"):
            visualisations.rating_histogram()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        plt.gcf().savefig(args.output, dpi=160, metadata={"Software": "Matplotlib"})
        print("Rendered the project's rating histogram from 12 synthetic review events.")
        print("SQLite fixture and MongoDB double; no external services contacted.")
    finally:
        plt.close("all")
        sql.close()


if __name__ == "__main__":
    main()
