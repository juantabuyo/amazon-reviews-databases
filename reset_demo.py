"""Explicitly clear only the named local demonstration stores."""
import argparse
import config
from database_connections import connect_mysql, connect_mongo, connect_neo4j


def check_reset(confirmation):
    if confirmation != config.RESET_CONFIRMATION:
        raise ValueError('Reset requires the exact explicit confirmation token')


def reset_storage(connection, collection, confirmation):
    check_reset(confirmation)
    config.validate_storage_config()
    if collection.database.name != config.MONGO_DB or collection.name != config.MONGO_COLLECTION:
        raise ValueError('The supplied MongoDB collection is not the configured demonstration target')
    cursor = connection.cursor()
    try:
        # USE is explicit so a supplied connection's previous database cannot
        # change the target. Only these three demonstration tables are dropped.
        cursor.execute(f'USE `{config.MYSQL_DB}`')
        for table in ('reviews', 'articulos', 'usuarios'):
            cursor.execute(f'DROP TABLE IF EXISTS {table}')
        connection.commit()
        collection.drop()
    finally:
        cursor.close()


def reset_graph(driver, confirmation):
    check_reset(confirmation)
    config.validate_graph_config()
    with driver.session(database=config.NEO4J_DATABASE) as session:
        session.run('MATCH (n) DETACH DELETE n').consume()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stores', choices=('storage', 'graph', 'both'), required=True)
    parser.add_argument('--confirm', required=True, help='Must be RESET-LOCAL-DEMO')
    args = parser.parse_args()
    check_reset(args.confirm)
    config.validate_storage_config()
    config.validate_graph_config()
    connection = client = driver = None
    try:
        if args.stores in ('storage', 'both'):
            connection = connect_mysql()
            client, collection = connect_mongo()
            reset_storage(connection, collection, args.confirm)
            print('MySQL demonstration tables and the MongoDB demonstration collection were cleared.')
        if args.stores in ('graph', 'both'):
            driver = connect_neo4j()
            reset_graph(driver, args.confirm)
            print('The named Neo4j demonstration database was cleared.')
    except Exception as error:
        print(f'Reset stopped ({type(error).__name__}). Earlier steps may already have completed; reset is not atomic across stores.')
        raise SystemExit(1) from None
    finally:
        for resource in (connection, client, driver):
            if resource is not None:
                resource.close()


if __name__ == '__main__':
    main()
