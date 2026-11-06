"""Environment-only configuration for dedicated local demonstration databases."""
import os
import re
from urllib.parse import urlsplit

MYSQL_HOST = os.getenv('MYSQL_HOST', '127.0.0.1')
MYSQL_PORT = int(os.getenv('MYSQL_PORT', '3306'))
MYSQL_USER = os.getenv('MYSQL_USER', 'amazon_demo_user')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', '')
MYSQL_DB = os.getenv('MYSQL_DB', 'amazon_reviews_demo')
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://127.0.0.1:27017')
MONGO_DB = os.getenv('MONGO_DB', 'amazon_reviews_demo')
MONGO_COLLECTION = 'reviews_texto'
NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://127.0.0.1:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', '')
NEO4J_DATABASE = os.getenv('NEO4J_DATABASE', 'amazon-reviews-demo')
BATCH_SIZE = int(os.getenv('BATCH_SIZE', '1000'))
TOP_N_USERS = int(os.getenv('TOP_N_USERS', '30'))
RESET_CONFIRMATION = 'RESET-LOCAL-DEMO'


def validate_demo_name(name, engine):
    """Reject production/default names and unsafe identifier characters."""
    pattern = r'amazon-reviews-demo(?:-[a-z0-9]+)*' if engine == 'neo4j' else r'amazon_reviews_demo(?:_[a-z0-9]+)*'
    if re.fullmatch(pattern, name) is None:
        raise ValueError(f'{engine} requires a dedicated amazon-reviews-demo name (underscores for MySQL/MongoDB)')
    return name


def validate_local_uri(uri, engine):
    """Connect only to a single loopback demonstration service."""
    parsed = urlsplit(uri)
    schemes = ('mongodb',) if engine == 'mongodb' else ('bolt', 'neo4j')
    if parsed.scheme not in schemes or parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError(f'{engine} requires one local loopback URI')
    # Reject multi-host URI forms and a default database in the URI. The selected
    # dedicated database is always supplied separately by this project.
    if ',' in parsed.netloc or parsed.path not in ('', '/'):
        raise ValueError(f'{engine} URI must not select multiple hosts or a database')


def require_password(value, engine):
    if not value or value.startswith('DUMMY_'):
        raise ValueError(f'Set a real local demonstration password for {engine}; the example is not a credential')


def validate_storage_config():
    validate_demo_name(MYSQL_DB, 'mysql')
    validate_demo_name(MONGO_DB, 'mongodb')
    if MYSQL_HOST not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('MySQL requires a local loopback host')
    validate_local_uri(MONGO_URI, 'mongodb')
    if not 1 <= MYSQL_PORT <= 65535 or BATCH_SIZE < 1:
        raise ValueError('Invalid MySQL port or batch size')


def validate_graph_config():
    validate_demo_name(NEO4J_DATABASE, 'neo4j')
    validate_local_uri(NEO4J_URI, 'neo4j')
    if TOP_N_USERS < 1:
        raise ValueError('TOP_N_USERS must be positive')
