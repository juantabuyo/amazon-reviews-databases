"""Local checks: synthetic query results and an isolated SQLite query fixture.

These checks do not validate MySQL/MongoDB connections or source datasets.
"""

from contextlib import redirect_stdout
from importlib.util import find_spec
from io import StringIO
import sqlite3
import unittest
from unittest.mock import MagicMock, patch

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import popularity_recommendations as recommendations
import visualisations as views


class SQLiteCursor:
    """Adapt only the placeholder convention for the recommendation query."""

    def __init__(self, connection):
        self.cursor = connection.cursor()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.cursor.close()

    def execute(self, sql, parameters):
        return self.cursor.execute(sql.replace("%s", "?"), parameters)

    def fetchall(self):
        return self.cursor.fetchall()


class SQLiteConnection:
    def __init__(self, connection):
        self.connection = connection

    def cursor(self):
        return SQLiteCursor(self.connection)


class ViewChecks(unittest.TestCase):
    def tearDown(self):
        plt.close("all")

    def test_read_connection_is_closed_after_query_error(self):
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value.execute.side_effect = RuntimeError()
        with patch.object(views, "connect_mysql", return_value=connection):
            with self.assertRaises(RuntimeError):
                views.query_rows("SELECT ignored")
        connection.close.assert_called_once()

    def test_six_sql_views_render_with_synthetic_rows(self):
        examples = [
            (views.reviews_by_year, [(2020, 3), (2021, 5)]),
            (views.product_popularity, [("demo-a", 5), ("demo-b", 3)]),
            (views.rating_histogram, [(None, 2), (3.0, 1), (5.0, 4)]),
            (views.cumulative_reviews, [(1_600_000_000,), (1_600_000_100,)]),
            (views.reviews_per_reviewer, [(1, 4), (2, 2)]),
            (views.top_reviewers, [("SYNTHETIC NAME A", 5), ("SYNTHETIC NAME B", 3)]),
        ]
        with patch.object(views, "AVAILABLE_CATEGORIES", ["demo-category"]):
            for function, rows in examples:
                with self.subTest(view=function.__name__), \
                        patch.object(views, "query_rows", return_value=rows), \
                        patch.object(views, "choose_category", return_value="demo-category"), \
                        patch("builtins.input", return_value="1"), \
                        patch.object(plt, "show", side_effect=lambda: plt.gcf().canvas.draw()), \
                        redirect_stdout(StringIO()):
                    function()
                    axis = plt.gca()
                    self.assertTrue(axis.get_title())
                    if function is views.rating_histogram:
                        self.assertEqual(len(axis.patches), 2)
                        self.assertEqual([bar.get_height() for bar in axis.patches], [1, 4])
                    if function is views.top_reviewers:
                        labels = [label.get_text() for label in axis.get_yticklabels()]
                        self.assertEqual(labels, ["Reviewer 2", "Reviewer 1"])
                    plt.close("all")

    @unittest.skipUnless(find_spec("wordcloud"), "wordcloud is not installed")
    def test_word_cloud_renders_with_synthetic_mongo_documents(self):
        client, collection = MagicMock(), MagicMock()
        collection.find.return_value = [
            {"summary": "Reliable synthetic example with useful details"},
            {"summary": None}, {},
        ]
        with patch.object(views, "connect_mongo", return_value=(client, collection)), \
                patch.object(views, "choose_category", return_value="demo-category"), \
                patch.object(plt, "show", side_effect=lambda: plt.gcf().canvas.draw()):
            views.summary_word_cloud()
        self.assertEqual(len(plt.gca().images), 1)
        collection.find.assert_called_once_with(
            {"categoria": "demo-category"}, {"summary": 1, "_id": 0}
        )
        client.close.assert_called_once()

    def test_popularity_counts_records_and_excludes_already_reviewed_products(self):
        with sqlite3.connect(":memory:") as fixture:
            fixture.execute(
                "CREATE TABLE reviews (asin TEXT, overall REAL, categoria TEXT, reviewerID TEXT)"
            )
            fixture.executemany(
                "INSERT INTO reviews VALUES (?, ?, ?, ?)",
                [
                    ("already-reviewed", 5, "demo", "selected-reviewer"),
                    ("popular", 4, "demo", "reviewer-a"),
                    ("popular", 4, "demo", "reviewer-a"),
                    ("single-high-rating", 5, "demo", "reviewer-b"),
                    ("same-rating-a", 4, "demo", "reviewer-c"),
                    ("same-rating-b", 4, "demo", "reviewer-d"),
                    ("other-category", 5, "other", "reviewer-e"),
                ],
            )
            connection = SQLiteConnection(fixture)
            rows = recommendations.recommend_unreviewed_products(
                connection, "selected-reviewer", "demo"
            )
            self.assertEqual(
                rows,
                [("popular", 2, 4.0), ("single-high-rating", 1, 5.0),
                 ("same-rating-a", 1, 4.0), ("same-rating-b", 1, 4.0)],
            )
            self.assertEqual(
                recommendations.recommend_unreviewed_products(
                    connection, "selected-reviewer", "demo' OR 1=1 --"
                ),
                [],
            )

    def test_cli_errors_do_not_echo_connection_details(self):
        for module in (views, recommendations):
            output = StringIO()
            with self.subTest(module=module.__name__), \
                    patch.object(module, "connect_mysql", side_effect=RuntimeError("SYNTHETIC-PRIVATE-URI")), \
                    redirect_stdout(output):
                module.main()
            self.assertIn("RuntimeError", output.getvalue())
            self.assertNotIn("SYNTHETIC-PRIVATE-URI", output.getvalue())


if __name__ == "__main__":
    unittest.main()
