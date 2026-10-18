"""Independent cases for category reuse and connection cleanup; no live services."""
import sqlite3
import unittest
from unittest.mock import MagicMock, patch
import graph_analysis
import popularity_recommendations as recommendations


class Cursor:
    def __init__(self, connection): self.cursor = connection.cursor()
    def __enter__(self): return self
    def __exit__(self, *args): self.cursor.close()
    def execute(self, sql, parameters=()):
        self.cursor.execute(sql.replace('%s', '?'), parameters)
    def fetchall(self): return self.cursor.fetchall()
    def fetchone(self): return self.cursor.fetchone()


class RecommendationCategoryTests(unittest.TestCase):
    def test_later_category_with_only_existing_items_remains_selectable(self):
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        db.executescript("""
            CREATE TABLE articulos (asin TEXT, categoria TEXT);
            CREATE TABLE reviews (reviewerID TEXT, asin TEXT, categoria TEXT, overall REAL);
            INSERT INTO articulos VALUES ('shared-item', 'first-category');
            INSERT INTO reviews VALUES ('reviewer-a', 'shared-item', 'first-category', 4);
            INSERT INTO reviews VALUES ('reviewer-b', 'shared-item', 'later-category', 5);
        """)
        connection = MagicMock()
        connection.cursor.side_effect = lambda: Cursor(db)
        self.assertIn('later-category', recommendations.get_categories(connection))
        self.assertTrue(recommendations.category_exists(connection, 'later-category'))
        self.assertEqual(recommendations.recommend_unreviewed_products(
            connection, 'new-reviewer', 'later-category'), [('shared-item', 1, 5.0)])


class GraphCleanupTests(unittest.TestCase):
    def test_category_query_failure_closes_cursor_and_connection(self):
        connection, cursor = MagicMock(), MagicMock()
        connection.cursor.return_value = cursor
        cursor.execute.side_effect = RuntimeError('synthetic query failure')
        with patch.object(graph_analysis, 'connect_mysql', return_value=connection):
            with self.assertRaises(RuntimeError):
                graph_analysis.get_categories()
        cursor.close.assert_called_once()
        connection.close.assert_called_once()
