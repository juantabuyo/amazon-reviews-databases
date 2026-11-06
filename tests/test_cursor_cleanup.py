"""Regression tests: cursors are closed when a query fails and when the function returns normally."""
import unittest

import graph_analysis as graph


class FailingCursor:
    def __init__(self, fail):
        self.fail, self.closed = fail, False

    def execute(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError('simulated database error')

    def fetchall(self):
        return []

    def close(self):
        self.closed = True


class Connection:
    def __init__(self, fail):
        self.fail, self.cursors = fail, []

    def cursor(self):
        cursor = FailingCursor(self.fail)
        self.cursors.append(cursor)
        return cursor


CALLS = {
    'get_top_users': lambda c: graph.get_top_users(c),
    'get_user_ratings': lambda c: graph.get_user_ratings(c, 'u1'),
    'get_random_items': lambda c: graph.get_random_items(c, 'demo_books', 2),
    'get_item_ratings': lambda c: graph.get_item_ratings(c, 'a1'),
    'get_multi_category_users': lambda c: graph.get_multi_category_users(c),
    'get_popular_items': lambda c: graph.get_popular_items(c),
    'get_item_users': lambda c: graph.get_item_users(c, ['a1']),
}


class CursorCleanup(unittest.TestCase):
    def test_cursor_closed_after_failed_query(self):
        for name, call in CALLS.items():
            with self.subTest(function=name):
                connection = Connection(fail=True)
                with self.assertRaises(RuntimeError):
                    call(connection)
                self.assertEqual([c.closed for c in connection.cursors], [True])

    def test_cursor_closed_after_normal_return(self):
        for name, call in CALLS.items():
            with self.subTest(function=name):
                connection = Connection(fail=False)
                call(connection)
                self.assertTrue(all(c.closed for c in connection.cursors))
                self.assertEqual(len(connection.cursors), 1)


if __name__ == '__main__':
    unittest.main()
