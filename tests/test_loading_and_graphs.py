"""Local SQL fixtures and controlled MongoDB/Neo4j doubles, never real services."""
from contextlib import redirect_stdout
from io import StringIO
import json
from datetime import date
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock

import config
import graph_analysis as graphs
import load_data
import reset_demo

FIXTURE = Path(__file__).resolve().parents[1] / 'data' / 'synthetic_books.jsonl'


class SQLCursor:
    def __init__(self, connection):
        self.owner = connection
        self.cursor = connection.db.cursor()

    def execute(self, sql, parameters=()):
        self.owner.statements.append(sql)
        if sql.startswith('USE '):
            return
        return self.cursor.execute(sql.replace('%s', '?'), parameters)

    def executemany(self, sql, rows):
        self.owner.statements.append(sql)
        if self.owner.fail_reviews and 'INSERT INTO reviews' in sql:
            raise RuntimeError('Synthetic SQL insertion failure')
        converted = [tuple(value.isoformat() if isinstance(value, date) else value for value in row) for row in rows]
        return self.cursor.executemany(sql.replace('%s', '?'), converted)

    def fetchall(self):
        return self.cursor.fetchall()

    def fetchone(self):
        return self.cursor.fetchone()

    def close(self):
        self.cursor.close()


class SQLFixture:
    """SQLite executes retained DML with only placeholder syntax adapted."""
    def __init__(self):
        self.db = sqlite3.connect(':memory:')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE usuarios (reviewerID TEXT PRIMARY KEY, reviewerName TEXT);
        CREATE TABLE articulos (asin TEXT PRIMARY KEY, categoria TEXT);
        CREATE TABLE reviews (review_id INTEGER PRIMARY KEY,
          reviewerID TEXT REFERENCES usuarios(reviewerID), asin TEXT REFERENCES articulos(asin),
          overall REAL, helpful_1 INTEGER, helpful_2 INTEGER, unixReviewTime INTEGER,
          reviewTime DATE, categoria TEXT);
        ''')
        self.statements = []
        self.fail_reviews = False
        self.fail_commit_after_write = False
        self.rollbacks = 0

    def cursor(self):
        return SQLCursor(self)

    def commit(self):
        self.db.commit()
        if self.fail_commit_after_write:
            raise RuntimeError('Synthetic lost commit acknowledgement')

    def rollback(self):
        self.rollbacks += 1
        self.db.rollback()

    def close(self):
        self.db.close()


class MongoFixture:
    """A document-list double with an injectable ordered partial write."""
    def __init__(self, fail_after=None, fail_on_call=1):
        self.documents = []
        self.fail_after = fail_after
        self.fail_on_call = fail_on_call
        self.calls = 0
        self.dropped = False
        self.database = SimpleNamespace(name=config.MONGO_DB)
        self.name = config.MONGO_COLLECTION

    def insert_many(self, documents, ordered=True):
        assert ordered
        self.calls += 1
        for i, document in enumerate(documents):
            if self.calls == self.fail_on_call and self.fail_after == i:
                raise RuntimeError('Synthetic MongoDB partial write')
            self.documents.append(dict(document))

    def count_documents(self, query):
        return sum(all(document.get(key) == value for key, value in query.items())
                   for document in self.documents)

    def drop(self):
        self.dropped = True
        self.documents.clear()


class GraphResult:
    def __init__(self, row=None):
        self.row = row

    def single(self):
        return self.row

    def consume(self):
        return None


class GraphFixture:
    """A tiny labelled-graph double for scope, edge count and reset behaviour."""
    def __init__(self):
        self.nodes = set()
        self.edges = []
        self.queries = []
        self.databases = []
        self.fail_write = False

    def session(self, database=None):
        self.databases.append(database)
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def run(self, query, **parameters):
        self.queries.append(query)
        if 'DETACH DELETE' in query:
            self.nodes.clear(); self.edges.clear()
            return GraphResult()
        if 'RETURN count(n)' in query:
            return GraphResult({'count': len(self.nodes)})
        if 'COUNT(DISTINCT v)' in query:
            neighbours = {node: set() for node in self.nodes}
            for left, right in self.edges:
                neighbours[left].add(right)
                neighbours[right].add(left)
            if not neighbours:
                return GraphResult(None)
            user = min(neighbours, key=lambda n: (-len(neighbours[n]), n))
            return GraphResult({'usuario': user, 'vecinos': len(neighbours[user])})
        if self.fail_write:
            raise RuntimeError('Synthetic graph write failure')
        if query.startswith('CREATE (u:Usuario'):
            self.nodes.add(parameters['rid'])
        elif ':SIMILITUD' in query:
            self.edges.extend([(parameters['uid1'], parameters['uid2']),
                               (parameters['uid2'], parameters['uid1'])])
        return GraphResult()


class LoadingChecks(unittest.TestCase):
    def setUp(self):
        self.sql = SQLFixture()

    def tearDown(self):
        self.sql.close()

    def test_two_categories_retain_review_events_and_match_counts(self):
        mongo = MongoFixture()
        report = load_data.load_dataset(self.sql, mongo, FIXTURE, 'demo_books', batch_size=4)
        self.assertEqual(report['status'], 'complete_counts_match')
        self.assertEqual(report['mysql_category_count'], 9)
        self.assertEqual(report['mongodb_category_count'], 9)
        second = load_data.load_dataset(self.sql, mongo, FIXTURE.with_name('synthetic_sports.jsonl'),
                                        'demo_sports', batch_size=2)
        self.assertEqual(second['mysql_category_count'], 3)
        self.assertEqual(self.sql.db.execute('SELECT COUNT(*) FROM usuarios').fetchone()[0], 3)
        self.assertEqual(len(mongo.documents), 12)
        self.assertFalse(any('DROP' in sql.upper() for sql in self.sql.statements))
        with self.assertRaises(load_data.LoadFailure) as error:
            load_data.load_dataset(self.sql, mongo, FIXTURE, 'demo_books')
        self.assertEqual(error.exception.report['status'], 'stopped')
        self.assertEqual(len(mongo.documents), 12)

    def test_sql_failure_rolls_back_and_never_writes_mongo(self):
        self.sql.fail_reviews = True
        mongo = MongoFixture()
        with self.assertRaises(load_data.LoadFailure) as error:
            load_data.load_dataset(self.sql, mongo, FIXTURE, 'demo_books')
        batch = error.exception.report['failed_batch']
        self.assertEqual((batch['mysql'], batch['mongodb']), ('rolled_back', 'not_started'))
        self.assertEqual(self.sql.db.execute('SELECT COUNT(*) FROM usuarios').fetchone()[0], 0)
        self.assertEqual(mongo.documents, [])

    def test_partial_mongo_write_is_reported_and_sql_is_rolled_back(self):
        mongo = MongoFixture(fail_after=2)
        with self.assertRaises(load_data.LoadFailure) as error:
            load_data.load_dataset(self.sql, mongo, FIXTURE, 'demo_books')
        batch = error.exception.report['failed_batch']
        self.assertEqual(batch['mysql'], 'rolled_back')
        self.assertEqual(batch['mongodb'], 'partial_or_unknown')
        self.assertEqual(batch['mongodb_confirmed_count'], 2)
        self.assertEqual(self.sql.db.execute('SELECT COUNT(*) FROM reviews').fetchone()[0], 0)
        self.assertEqual(mongo.calls, 1)

    def test_previous_batches_remain_and_failure_is_not_retried(self):
        mongo = MongoFixture(fail_after=1, fail_on_call=2)
        with self.assertRaises(load_data.LoadFailure) as error:
            load_data.load_dataset(self.sql, mongo, FIXTURE, 'demo_books', batch_size=4)
        report = error.exception.report
        self.assertEqual(len(report['confirmed_batches']), 1)
        self.assertEqual(report['failed_batch']['mongodb_confirmed_count'], 1)
        self.assertEqual(self.sql.db.execute('SELECT COUNT(*) FROM reviews').fetchone()[0], 4)
        self.assertEqual(len(mongo.documents), 5)
        self.assertEqual(mongo.calls, 2)

    def test_lost_commit_acknowledgement_is_unknown_not_rolled_back(self):
        self.sql.fail_commit_after_write = True
        mongo = MongoFixture()
        with self.assertRaises(load_data.LoadFailure) as error:
            load_data.load_dataset(self.sql, mongo, FIXTURE, 'demo_books')
        batch = error.exception.report['failed_batch']
        self.assertEqual(batch['mysql'], 'unknown_after_commit_error')
        self.assertEqual(batch['mongodb'], 'confirmed')
        self.assertEqual(self.sql.db.execute('SELECT COUNT(*) FROM reviews').fetchone()[0], 9)

    def test_invalid_identifiers_rejected_before_any_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'invalid.jsonl'
            path.write_text(json.dumps({'reviewerID': '', 'asin': 'demo-a'}) + '\n')
            mongo = MongoFixture()
            with self.assertRaises(ValueError):
                load_data.load_dataset(self.sql, mongo, path, 'demo_books')
            self.assertEqual(self.sql.statements, [])
            self.assertEqual(mongo.documents, [])

    def test_duplicate_ratings_are_means_in_both_graph_queries(self):
        load_data.load_dataset(self.sql, MongoFixture(), FIXTURE, 'demo_books')
        self.assertEqual(graphs.get_user_ratings(self.sql, 'demo-user-1'), {'demo-book-a': 4.0, 'demo-book-b': 2.0})
        item = graphs.get_item_ratings(self.sql, 'demo-book-a')
        self.assertEqual(item[0], ('demo-user-1', 4.0, 1577923200))
        users, items = graphs.get_item_users(self.sql, ['demo-book-a'])
        self.assertEqual(users['demo-book-a'], ['demo-user-1', 'demo-user-2'])
        self.assertEqual(items['demo-user-1'], {'demo-book-a'})


class GraphAndResetChecks(unittest.TestCase):
    def test_three_nodes_bidirectional_edges_count_distinct_neighbours(self):
        graph = GraphFixture()
        output = StringIO()
        with redirect_stdout(output):
            graphs.load_similarities(graph, ['demo-a', 'demo-b', 'demo-c'],
                                     [('demo-a', 'demo-b', 0.5), ('demo-a', 'demo-c', 0.8)])
            graphs.show_most_connected_user(graph)
        self.assertEqual(len(graph.edges), 4)
        self.assertIn('(2 neighbours)', output.getvalue())
        self.assertTrue(all(name == config.NEO4J_DATABASE for name in graph.databases))
        self.assertFalse(any('DELETE' in query for query in graph.queries))
        with self.assertRaises(ValueError):
            graphs.load_similarities(graph, ['demo-d'], [])
        self.assertEqual(graph.nodes, {'demo-a', 'demo-b', 'demo-c'})

    def test_graph_write_error_does_not_print_success(self):
        graph = GraphFixture()
        graph.fail_write = True
        output = StringIO()
        with redirect_stdout(output), self.assertRaises(RuntimeError):
            graphs.load_similarities(graph, ['demo-a'], [])
        self.assertNotIn('Loaded', output.getvalue())

    def test_reset_rejects_default_databases_and_requires_explicit_token(self):
        for engine, name in [('mysql', 'production'), ('mongodb', 'admin'), ('neo4j', 'neo4j'),
                             ('mysql', 'amazon_reviews_demo;DROP DATABASE production')]:
            with self.subTest(engine=engine), self.assertRaises(ValueError):
                config.validate_demo_name(name, engine)
        graph = GraphFixture()
        graph.nodes.add('demo-a')
        with self.assertRaises(ValueError):
            reset_demo.reset_graph(graph, 'wrong-token')
        self.assertEqual(graph.queries, [])
        with patch.object(config, 'NEO4J_DATABASE', 'neo4j'), self.assertRaises(ValueError):
            reset_demo.reset_graph(graph, config.RESET_CONFIRMATION)
        self.assertEqual(graph.queries, [])
        reset_demo.reset_graph(graph, config.RESET_CONFIRMATION)
        self.assertEqual(graph.nodes, set())
        self.assertEqual(graph.databases, [config.NEO4J_DATABASE])

    def test_storage_reset_drops_only_the_three_demo_tables(self):
        sql = SQLFixture()
        mongo = MongoFixture()
        try:
            with self.assertRaises(ValueError):
                reset_demo.reset_storage(sql, mongo, 'wrong-token')
            self.assertEqual(sql.statements, [])
            mongo.database.name = 'production'
            with self.assertRaises(ValueError):
                reset_demo.reset_storage(sql, mongo, config.RESET_CONFIRMATION)
            self.assertEqual(sql.statements, [])
            self.assertFalse(mongo.dropped)
            mongo.database.name = config.MONGO_DB
            reset_demo.reset_storage(sql, mongo, config.RESET_CONFIRMATION)
            self.assertEqual(sql.statements[0], f'USE `{config.MYSQL_DB}`')
            self.assertEqual(sql.statements[1:], ['DROP TABLE IF EXISTS reviews', 'DROP TABLE IF EXISTS articulos', 'DROP TABLE IF EXISTS usuarios'])
            self.assertTrue(mongo.dropped)
        finally:
            sql.close()

    def test_graph_options_close_sql_if_graph_connection_fails(self):
        for option in (graphs.similarities_option, graphs.random_items_option,
                       graphs.multi_category_option, graphs.popular_items_option):
            sql = MagicMock()
            with patch.object(graphs, 'connect_mysql', return_value=sql), \
                    patch.object(graphs, 'connect_neo4j', side_effect=RuntimeError('Synthetic unavailable service')), \
                    redirect_stdout(StringIO()), self.assertRaises(RuntimeError):
                option()
            sql.close.assert_called_once()

    def test_coursework_similarity_formula_and_degenerate_cases(self):
        self.assertAlmostEqual(graphs.pearson_correlation({'a': 2, 'b': 4}, {'a': 3, 'b': 5}), 1.0)
        self.assertIsNone(graphs.pearson_correlation({'a': 1}, {'b': 2}))
        self.assertIsNone(graphs.pearson_correlation({'a': 3}, {'a': 3}))


if __name__ == '__main__':
    unittest.main()
