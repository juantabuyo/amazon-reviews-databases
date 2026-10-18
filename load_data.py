"""Load review events into MySQL and MongoDB, stopping on the first failed batch.

The two stores do not share a transaction. A failed batch may leave MongoDB
partly written, or SQL commit status uncertain; the report never calls that a
successful load. Previously committed batches remain in both stores.
"""
import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import uuid

import config
from database_connections import connect_mysql, connect_mongo

USER_SQL = 'INSERT INTO usuarios (reviewerID, reviewerName) VALUES (%s, %s)'
ITEM_SQL = 'INSERT INTO articulos (asin, categoria) VALUES (%s, %s)'
REVIEW_SQL = '''INSERT INTO reviews
    (reviewerID, asin, overall, helpful_1, helpful_2, unixReviewTime, reviewTime, categoria)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)'''


class LoadFailure(RuntimeError):
    """A safe summary of a failed load, without credentials or review text."""
    def __init__(self, report):
        super().__init__('Loading stopped; inspect the per-engine states in the load report')
        self.report = report


def read_reviews(path):
    """Stream JSONL objects; invalid input raises instead of being silently skipped."""
    with Path(path).open(encoding='utf-8') as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                review = json.loads(line)
            except json.JSONDecodeError:
                raise ValueError(f'Invalid JSON on line {line_number}') from None
            if not isinstance(review, dict):
                raise ValueError(f'Expected a JSON object on line {line_number}')
            yield review


def parse_date(value):
    """Retain the submission's nullable date policy for missing or invalid dates."""
    try:
        return datetime.strptime(value.strip(), '%m %d, %Y').date()
    except (ValueError, AttributeError):
        return None


def validate_review(review, category):
    """Validate identifiers before creating foreign-key rows or queuing a batch."""
    if not isinstance(category, str) or not 1 <= len(category) <= 64:
        raise ValueError('A category must contain 1 to 64 characters')
    for key, maximum in [('reviewerID', 64), ('asin', 32)]:
        value = review.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise ValueError(f'{key} must be a non-empty string of at most {maximum} characters')
    for key in ('reviewerName', 'reviewText', 'summary'):
        if review.get(key) is not None and not isinstance(review[key], str):
            raise ValueError(f'{key} must be a string or null')
    if len(review.get('reviewerName') or '') > 255:
        raise ValueError('reviewerName exceeds the SQL field length')
    rating = review.get('overall')
    if rating is not None and (isinstance(rating, bool) or not isinstance(rating, (int, float))
                               or not math.isfinite(rating) or not 1 <= rating <= 5):
        raise ValueError('overall must be null or a finite number from 1 to 5')
    timestamp = review.get('unixReviewTime')
    if timestamp is not None and (isinstance(timestamp, bool) or not isinstance(timestamp, int)
                                  or not -(2 ** 63) <= timestamp < 2 ** 63):
        raise ValueError('unixReviewTime must be null or a signed 64-bit integer')
    helpful = review.get('helpful')
    if helpful is not None:
        if (not isinstance(helpful, list) or len(helpful) != 2
                or any(isinstance(v, bool) or not isinstance(v, int) or not 0 <= v < 2 ** 31 for v in helpful)
                or helpful[0] > helpful[1]):
            raise ValueError('helpful must be null or [helpful_votes, total_votes] with valid non-negative counts')


def validate_file(path, category):
    count = 0
    for review in read_reviews(path):
        validate_review(review, category)
        count += 1
    return count


def initialise_schema(connection, collection):
    """Create missing tables/indices only; never drop or clear existing data."""
    config.validate_storage_config()
    cursor = connection.cursor()
    try:
        cursor.execute(f'CREATE DATABASE IF NOT EXISTS `{config.MYSQL_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
        cursor.execute(f'USE `{config.MYSQL_DB}`')
        schema = Path(__file__).with_name('schema.sql').read_text()
        for statement in schema.split(';'):
            if statement.strip():
                cursor.execute(statement)
        cursor.execute('SHOW INDEX FROM reviews')
        existing = {row[2] for row in cursor.fetchall()}
        for name, column in [('idx_reviews_categoria', 'categoria'), ('idx_reviews_asin', 'asin'),
                             ('idx_reviews_reviewerID', 'reviewerID'), ('idx_reviews_overall', 'overall'),
                             ('idx_reviews_unix', 'unixReviewTime')]:
            if name not in existing:
                cursor.execute(f'CREATE INDEX {name} ON reviews({column})')
        connection.commit()
        for field in ('categoria', 'reviewerID', 'asin'):
            collection.create_index(field)
        collection.create_index([('_load_id', 1), ('_batch_number', 1)])
    finally:
        cursor.close()


def _rollback(connection, state):
    try:
        connection.rollback()
        # A commit error can mean that the server committed but the acknowledgement
        # was lost. A subsequent rollback cannot establish that it did not commit.
        if state['mysql'] != 'unknown_after_commit_error':
            state['mysql'] = 'rolled_back'
    except Exception:
        state['mysql'] = 'unknown_after_rollback_error'


def flush_batch(connection, cursor, collection, users, items, rows, documents,
                load_id, batch_number):
    """Write a batch, commit SQL only after Mongo acknowledgement, report failures.

    There is no automatic retry or compensation: either could duplicate events or
    hide partial writes. The caller stops and retains the report for recovery.
    """
    state = {'batch_number': batch_number, 'attempted_reviews': len(rows),
             'mysql': 'not_started', 'mongodb': 'not_started',
             'mongodb_confirmed_count': 0}
    if not rows:
        return state
    tagged = [dict(document, _load_id=load_id, _batch_number=batch_number)
              for document in documents]
    phase = 'sql_statements'
    try:
        state['mysql'] = 'pending'
        if users:
            cursor.executemany(USER_SQL, users)
        if items:
            cursor.executemany(ITEM_SQL, items)
        cursor.executemany(REVIEW_SQL, rows)
        phase = 'mongo_insert'
        state['mongodb'] = 'partial_or_unknown'
        collection.insert_many(tagged, ordered=True)
        state['mongodb_confirmed_count'] = collection.count_documents(
            {'_load_id': load_id, '_batch_number': batch_number})
        if state['mongodb_confirmed_count'] != len(rows):
            raise RuntimeError('MongoDB batch count did not match the attempted reviews')
        state['mongodb'] = 'confirmed'
        phase = 'sql_commit'
        connection.commit()
        state['mysql'] = 'committed'
    except Exception as error:
        if phase == 'sql_commit':
            state['mysql'] = 'unknown_after_commit_error'
        _rollback(connection, state)
        if state['mongodb'] == 'partial_or_unknown':
            try:
                state['mongodb_confirmed_count'] = collection.count_documents(
                    {'_load_id': load_id, '_batch_number': batch_number})
            except Exception:
                state['mongodb_confirmed_count'] = None
        state['failure_phase'] = phase
        state['error_type'] = type(error).__name__
        raise LoadFailure(state) from None
    return state


def load_dataset(connection, collection, path, category, batch_size=None):
    """Append one previously absent category, reusing the submitted schema.

    Review rows are events: repeated user/item pairs are retained. Graph ratings
    aggregate them separately. Rerunning an existing category is refused.
    """
    size = config.BATCH_SIZE if batch_size is None else batch_size
    if size < 1:
        raise ValueError('batch_size must be positive')
    report = {'status': 'in_progress', 'category': category, 'load_id': uuid.uuid4().hex,
              'review_policy': 'retain_events; mean_rating_per_user_item_for_graphs',
              'validated_input_reviews': 0, 'confirmed_batches': [], 'failed_batch': None}
    # Validate the entire stream before any writes. A changed file or I/O error on
    # the second pass is still reported; earlier committed batches are not undone.
    report['validated_input_reviews'] = validate_file(path, category)
    cursor = connection.cursor()
    try:
        cursor.execute('SELECT COUNT(*) FROM reviews WHERE categoria = %s', (category,))
        if cursor.fetchone()[0] or collection.count_documents({'categoria': category}):
            raise ValueError('The category already exists in at least one store; no data were appended')
        cursor.execute('SELECT reviewerID FROM usuarios')
        seen_users = {row[0] for row in cursor.fetchall()}
        cursor.execute('SELECT asin FROM articulos')
        seen_items = {row[0] for row in cursor.fetchall()}
        users, items, rows, documents = [], [], [], []

        def flush():
            if rows:
                state = flush_batch(connection, cursor, collection, users, items, rows, documents,
                                    report['load_id'], len(report['confirmed_batches']) + 1)
                report['confirmed_batches'].append(state)
                users.clear(); items.clear(); rows.clear(); documents.clear()

        for review in read_reviews(path):
            validate_review(review, category)
            reviewer, asin = review['reviewerID'], review['asin']
            if reviewer not in seen_users:
                users.append((reviewer, review.get('reviewerName')))
                seen_users.add(reviewer)
            if asin not in seen_items:
                items.append((asin, category))
                seen_items.add(asin)
            helpful_1, helpful_2 = review.get('helpful') or (None, None)
            rows.append((reviewer, asin, review.get('overall'), helpful_1, helpful_2,
                         review.get('unixReviewTime'), parse_date(review.get('reviewTime')), category))
            documents.append({key: review.get(key) for key in
                              ('reviewerID', 'asin', 'reviewText', 'summary', 'unixReviewTime')})
            documents[-1]['categoria'] = category
            if len(rows) == size:
                flush()
        flush()
        cursor.execute('SELECT COUNT(*) FROM reviews WHERE categoria = %s', (category,))
        report['mysql_category_count'] = cursor.fetchone()[0]
        report['mongodb_category_count'] = collection.count_documents({'categoria': category})
        expected = report['validated_input_reviews']
        if report['mysql_category_count'] != expected or report['mongodb_category_count'] != expected:
            report['status'] = 'failed_final_count_check'
            raise LoadFailure(report)
        report['status'] = 'complete_counts_match'
        return report
    except LoadFailure as error:
        if error.report is report:
            raise
        report['failed_batch'] = error.report
        report['status'] = 'failed_batch_do_not_retry_blindly'
        raise LoadFailure(report) from None
    except Exception as error:
        # ValueError before writes or an unexpected later input/read error: no
        # success claim, and retain previously confirmed batch counts.
        try:
            connection.rollback()
        except Exception:
            report['rollback_status'] = 'unknown_after_rollback_error'
        report['status'] = 'stopped'
        report['error_type'] = type(error).__name__
        report['error_message'] = str(error) if isinstance(error, ValueError) else 'See the error type; raw driver messages are not logged'
        raise LoadFailure(report) from None
    finally:
        cursor.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init', help='Create missing demo tables and indices; never reset data')
    validate = sub.add_parser('validate', help='Validate JSONL locally; opens no database')
    load = sub.add_parser('load', help='Load one new category and write a per-engine report')
    for command in (validate, load):
        command.add_argument('--file', type=Path, required=True)
        command.add_argument('--category', required=True)
    load.add_argument('--report', type=Path, default=Path('load_report.json'))
    args = parser.parse_args()
    if args.command == 'validate':
        print(json.dumps({'status': 'validated_locally', 'reviews': validate_file(args.file, args.category)}))
        return
    connection = None
    client = None
    try:
        connection = connect_mysql(select_database=args.command != 'init')
        client, collection = connect_mongo()
        if args.command == 'init':
            initialise_schema(connection, collection)
            print('Demo schema and indices created or already present. Existing rows were retained.')
        else:
            report = load_dataset(connection, collection, args.file, args.category)
            args.report.write_text(json.dumps(report, indent=2) + '\n')
            print(f'Load complete: {report["mysql_category_count"]} SQL rows and {report["mongodb_category_count"]} MongoDB documents.')
    except LoadFailure as error:
        args.report.write_text(json.dumps(error.report, indent=2) + '\n')
        print('Load stopped. A report was written; inspect partial/unknown states before recovery.')
        raise SystemExit(1) from None
    except Exception as error:
        print(f'Operation stopped ({type(error).__name__}); raw connection details are not displayed.')
        raise SystemExit(1) from None
    finally:
        if connection is not None:
            connection.close()
        if client is not None:
            client.close()


if __name__ == '__main__':
    main()
