"""Connection creation is explicit; importing this module opens no service."""
import pymysql
import pymongo
from neo4j import GraphDatabase
import config


def connect_mysql(select_database=True):
    config.validate_storage_config()
    config.require_password(config.MYSQL_PASSWORD, 'MySQL')
    options = dict(host=config.MYSQL_HOST, port=config.MYSQL_PORT,
                   user=config.MYSQL_USER, password=config.MYSQL_PASSWORD,
                   charset='utf8mb4', autocommit=False, connect_timeout=5)
    if select_database:
        options['database'] = config.MYSQL_DB
    return pymysql.connect(**options)


def connect_mongo():
    config.validate_storage_config()
    client = pymongo.MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=5000,
                                connectTimeoutMS=5000)
    return client, client[config.MONGO_DB][config.MONGO_COLLECTION]


def connect_neo4j():
    config.validate_graph_config()
    config.require_password(config.NEO4J_PASSWORD, 'Neo4j')
    return GraphDatabase.driver(config.NEO4J_URI,
                                auth=(config.NEO4J_USER, config.NEO4J_PASSWORD),
                                connection_timeout=5)
