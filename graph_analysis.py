"""Graph analyses of review relationships.

Graph creation requires an empty, explicitly named local demonstration database.
No option clears an existing graph. Use the separate reset command if needed.
"""
from contextlib import closing
from config import NEO4J_DATABASE, TOP_N_USERS, validate_graph_config
from database_connections import connect_mysql, connect_neo4j

def require_empty_graph(driver):
    validate_graph_config()
    with driver.session(database=NEO4J_DATABASE) as session:
        count = session.run('MATCH (n) RETURN count(n) AS count').single()['count']
    if count:
        raise ValueError('The demo graph is not empty; use the explicit reset command before choosing a different graph view')
import math
import random
from itertools import combinations
AVAILABLE_CATEGORIES = []

def get_categories():
    with closing(connect_mysql()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute('SELECT DISTINCT categoria FROM reviews ORDER BY categoria')
            return [row[0] for row in cursor.fetchall()]

def get_top_users(conn, n=TOP_N_USERS):
    cursor = conn.cursor()
    sql = """
        SELECT reviewerID, COUNT(*) AS total
        FROM reviews
        GROUP BY reviewerID
        ORDER BY total DESC, reviewerID ASC
        LIMIT %s
    """
    cursor.execute(sql, (n,))
    users = [row[0] for row in cursor.fetchall()]
    cursor.close()
    return users

def get_user_ratings(conn, reviewer_id):
    """
Average non-null review events per user/item pair; SQL order cannot choose an arbitrary rating."""
    cursor = conn.cursor()
    sql = 'SELECT asin, AVG(overall) FROM reviews WHERE reviewerID = %s AND overall IS NOT NULL GROUP BY asin ORDER BY asin'
    cursor.execute(sql, (reviewer_id,))
    ratings = {row[0]: float(row[1]) for row in cursor.fetchall()}
    cursor.close()
    return ratings

def pearson_correlation(ratings_u, ratings_v):
    """Calculate the submitted centred similarity on shared items.

Each mean uses all of that user's item ratings, not only the intersection.
This is the coursework formula, not ordinary Pearson recomputed on co-rated items.
Return None when no common items or no non-zero denominator exist."""
    common = set(ratings_u.keys()) & set(ratings_v.keys())
    if len(common) == 0:
        return None
    mean_u = sum(ratings_u.values()) / len(ratings_u)
    mean_v = sum(ratings_v.values()) / len(ratings_v)
    numerator = 0.0
    sum_sq_u = 0.0
    sum_sq_v = 0.0
    for item in sorted(common):
        diff_u = ratings_u[item] - mean_u
        diff_v = ratings_v[item] - mean_v
        numerator += diff_u * diff_v
        sum_sq_u += diff_u ** 2
        sum_sq_v += diff_v ** 2
    denominator = math.sqrt(sum_sq_u) * math.sqrt(sum_sq_v)
    if denominator == 0:
        return None
    return numerator / denominator

def calculate_similarities(conn, users):
    """Evaluate each pair among the selected most-active users."""
    print(f'Calculating similarities among {len(users)} users...')
    ratings = {}
    for uid in users:
        ratings[uid] = get_user_ratings(conn, uid)
    similarities = []
    total_pairs = len(users) * (len(users) - 1) // 2
    processed = 0
    for u, v in combinations(users, 2):
        pc = pearson_correlation(ratings[u], ratings[v])
        if pc is not None:
            similarities.append((u, v, round(pc, 4)))
        processed += 1
        if processed % 100 == 0:
            print(f'  {processed}/{total_pairs} pairs processed...')
    print(f'Similarities calculated: {len(similarities)} pairs with common items')
    return similarities

def load_similarities(driver, users, similarities):
    """Create two directed similarity relationships per pair in an empty demo graph."""
    require_empty_graph(driver)
    with driver.session(database=NEO4J_DATABASE) as session:
        for uid in users:
            session.run('CREATE (u:Usuario {reviewerID: $rid})', rid=uid).consume()
        for u, v, sim in similarities:
            session.run("""
                MATCH (u1:Usuario {reviewerID: $uid1})
                MATCH (u2:Usuario {reviewerID: $uid2})
                CREATE (u1)-[:SIMILITUD {valor: $sim}]->(u2)
                CREATE (u2)-[:SIMILITUD {valor: $sim}]->(u1)
            """, uid1=u, uid2=v, sim=sim).consume()
    print(f'Loaded {len(users)} nodes and {len(similarities) * 2} relationships in Neo4j')

def show_most_connected_user(driver):
    """Count distinct neighbouring users, not the two directed relationships."""
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run("""
            MATCH (u:Usuario)-[:SIMILITUD]-(v:Usuario)
            RETURN u.reviewerID AS usuario, COUNT(DISTINCT v) AS vecinos
            ORDER BY vecinos DESC, usuario ASC
            LIMIT 1
        """)
        record = result.single()
        if record:
            print(f"\nUser with most distinct neighbours: {record['usuario']} ({record['vecinos']} neighbours)")
        else:
            print('No results found')

def similarities_option():
    print('\n' + '=' * 60)
    print('4.1 - USER SIMILARITY (COURSEWORK CENTRED FORMULA)')
    print('=' * 60)
    with closing(connect_mysql()) as conn, closing(connect_neo4j()) as driver:
        users = get_top_users(conn, TOP_N_USERS)
        print(f'Top {TOP_N_USERS} users selected')
        similarities = calculate_similarities(conn, users)
        load_similarities(driver, users, similarities)
        show_most_connected_user(driver)
        print('\nInspect the dedicated demonstration database in your local Neo4j Browser.')

def choose_category():
    print('\nAvailable categories:')
    for i, cat in enumerate(AVAILABLE_CATEGORIES, 1):
        print(f'  {i}. {cat}')
    if not AVAILABLE_CATEGORIES:
        raise ValueError('No categories are available; load the fixture first')
    while True:
        try:
            option = int(input('Select a category: '))
            if 1 <= option <= len(AVAILABLE_CATEGORIES):
                return AVAILABLE_CATEGORIES[option - 1]
            print('Invalid option')
        except ValueError:
            print('Enter a number')

def get_random_items(conn, category, n):
    """Sample items reproducibly when the caller seeds random."""
    cursor = conn.cursor()
    sql = """
        SELECT DISTINCT asin
        FROM reviews
        WHERE categoria = %s
        ORDER BY asin
    """
    cursor.execute(sql, (category,))
    all_items = [row[0] for row in cursor.fetchall()]
    cursor.close()
    if len(all_items) < n:
        print(f'There are only {len(all_items)} items in {category}; all will be used')
        return all_items
    return random.sample(all_items, n)

def get_item_ratings(conn, asin):
    """Return one row per user/item, with mean rating and latest known event timestamp."""
    cursor = conn.cursor()
    sql = """
        SELECT reviewerID, AVG(overall), MAX(unixReviewTime)
        FROM reviews
        WHERE asin = %s AND overall IS NOT NULL
        GROUP BY reviewerID ORDER BY reviewerID
    """
    cursor.execute(sql, (asin,))
    results = cursor.fetchall()
    cursor.close()
    return results

def load_items_and_users(driver, item_data):
    """Write items, users and their aggregated ratings into an empty demo graph."""
    require_empty_graph(driver)
    with driver.session(database=NEO4J_DATABASE) as session:
        created_users = set()
        for asin, reviews in item_data.items():
            session.run('CREATE (a:Articulo {asin: $asin})', asin=asin).consume()
            for reviewer_id, overall, unix_time in reviews:
                if reviewer_id not in created_users:
                    session.run('CREATE (u:Usuario {reviewerID: $rid})', rid=reviewer_id).consume()
                    created_users.add(reviewer_id)
                session.run("""
                    MATCH (u:Usuario {reviewerID: $rid})
                    MATCH (a:Articulo {asin: $asin})
                    CREATE (u)-[:HA_PUNTUADO {nota: $nota, timestamp: $ts}]->(a)
                """, rid=reviewer_id, asin=asin, nota=float(overall), ts=unix_time).consume()
    total_relationships = sum((len(v) for v in item_data.values()))
    print(f'Loaded {len(item_data)} items and {len(created_users)} users ({total_relationships} relationships)')

def random_items_option():
    print('\n' + '=' * 60)
    print('4.2 - RANDOM ITEMS AND THEIR REVIEWERS')
    print('=' * 60)
    with closing(connect_mysql()) as conn, closing(connect_neo4j()) as driver:
        category = choose_category()
        while True:
            try:
                n = int(input('Number of random items to select: '))
                if n > 0:
                    break
                print('Must be greater than zero')
            except ValueError:
                print('Enter a valid number')
        items = get_random_items(conn, category, n)
        print(f'Selected items: {items}')
        item_data = {}
        for asin in items:
            item_data[asin] = get_item_ratings(conn, asin)
        load_items_and_users(driver, item_data)
        print('\nGraph load completed. Inspect the dedicated demonstration database in your local Neo4j Browser.')

def get_multi_category_users(conn, n_users=400):
    """Inspect the first n users by name and retain those reviewing two or more categories."""
    cursor = conn.cursor()
    sql = """
        SELECT reviewerID
        FROM usuarios
        ORDER BY reviewerName, reviewerID
        LIMIT %s
    """
    cursor.execute(sql, (n_users,))
    user_ids = [row[0] for row in cursor.fetchall()]
    if not user_ids:
        cursor.close()
        return {}
    result = {}
    placeholders = ','.join(['%s'] * len(user_ids))
    sql = f'\n        SELECT reviewerID, categoria, COUNT(DISTINCT asin) AS total\n        FROM reviews\n        WHERE reviewerID IN ({placeholders})\n        GROUP BY reviewerID, categoria\n    '
    cursor.execute(sql, user_ids)
    data_by_user = {}
    for rid, cat, total in cursor.fetchall():
        if rid not in data_by_user:
            data_by_user[rid] = {}
        data_by_user[rid][cat] = total
    cursor.close()
    for rid, cats in data_by_user.items():
        if len(cats) >= 2:
            result[rid] = cats
    return result

def load_users_and_categories(driver, user_categories):
    """Write users, categories and distinct-item counts into an empty demo graph."""
    require_empty_graph(driver)
    with driver.session(database=NEO4J_DATABASE) as session:
        created_categories = set()
        for rid, categories in user_categories.items():
            session.run('CREATE (u:Usuario {reviewerID: $rid})', rid=rid).consume()
            for cat, count in categories.items():
                if cat not in created_categories:
                    session.run('CREATE (t:TipoArticulo {nombre: $nombre})', nombre=cat).consume()
                    created_categories.add(cat)
                session.run("""
                    MATCH (u:Usuario {reviewerID: $rid})
                    MATCH (t:TipoArticulo {nombre: $cat})
                    CREATE (u)-[:HA_CONSUMIDO {cantidad: $cnt}]->(t)
                """, rid=rid, cat=cat, cnt=count).consume()
    print(f'Loaded {len(user_categories)} users and {len(created_categories)} item categories')

def multi_category_option():
    print('\n' + '=' * 60)
    print('4.3 - USERS REVIEWING MULTIPLE CATEGORIES')
    print('=' * 60)
    with closing(connect_mysql()) as conn, closing(connect_neo4j()) as driver:
        user_categories = get_multi_category_users(conn, 400)
        print(f'Users reviewing multiple categories: {len(user_categories)}')
        load_users_and_categories(driver, user_categories)
        print('\nGraph load completed. Inspect the dedicated demonstration database in your local Neo4j Browser.')

def get_popular_items(conn, top=5, max_reviews=40):
    """Return the most-reviewed items below the submitted max-review threshold."""
    cursor = conn.cursor()
    sql = """
        SELECT asin, COUNT(*) AS total
        FROM reviews
        GROUP BY asin
        HAVING total < %s
        ORDER BY total DESC, asin ASC
        LIMIT %s
    """
    cursor.execute(sql, (max_reviews, top))
    items = [row[0] for row in cursor.fetchall()]
    cursor.close()
    return items

def get_item_users(conn, items):
    """Return distinct users per item and sets of items per user."""
    cursor = conn.cursor()
    item_users = {}
    user_items = {}
    for asin in items:
        cursor.execute('SELECT DISTINCT reviewerID FROM reviews WHERE asin = %s ORDER BY reviewerID', (asin,))
        users = [row[0] for row in cursor.fetchall()]
        item_users[asin] = users
        for uid in users:
            if uid not in user_items:
                user_items[uid] = set()
            user_items[uid].add(asin)
    cursor.close()
    return (item_users, user_items)

def load_popular_items(driver, items, item_users, user_items):
    """Write popular items and the number of items shared by each user pair."""
    require_empty_graph(driver)
    with driver.session(database=NEO4J_DATABASE) as session:
        for asin in items:
            session.run('CREATE (a:Articulo {asin: $asin})', asin=asin).consume()
        all_users = set()
        for asin, users in item_users.items():
            for uid in users:
                if uid not in all_users:
                    session.run('CREATE (u:Usuario {reviewerID: $rid})', rid=uid).consume()
                    all_users.add(uid)
                session.run("""
                    MATCH (u:Usuario {reviewerID: $rid})
                    MATCH (a:Articulo {asin: $asin})
                    CREATE (u)-[:HA_PUNTUADO]->(a)
                """, rid=uid, asin=asin).consume()
        user_list = sorted(all_users)
        created_relationships = 0
        for i in range(len(user_list)):
            for j in range(i + 1, len(user_list)):
                u1 = user_list[i]
                u2 = user_list[j]
                common = user_items.get(u1, set()) & user_items.get(u2, set())
                if len(common) > 0:
                    session.run("""
                        MATCH (u1:Usuario {reviewerID: $uid1})
                        MATCH (u2:Usuario {reviewerID: $uid2})
                        CREATE (u1)-[:ARTICULOS_COMUNES {cantidad: $cnt}]->(u2)
                    """, uid1=u1, uid2=u2, cnt=len(common)).consume()
                    created_relationships += 1
    print(f'Loaded {len(items)} items, {len(all_users)} users, {created_relationships} relationships between users')

def popular_items_option():
    print('\n' + '=' * 60)
    print('4.4 - POPULAR ITEMS AND SHARED ITEMS')
    print('=' * 60)
    with closing(connect_mysql()) as conn, closing(connect_neo4j()) as driver:
        items = get_popular_items(conn, top=5, max_reviews=40)
        print(f'Five most-reviewed items with fewer than 40 reviews: {items}')
        item_users, user_items = get_item_users(conn, items)
        load_popular_items(driver, items, item_users, user_items)
        print('\nGraph load completed. Inspect the dedicated demonstration database in your local Neo4j Browser.')

def show_menu():
    print('\n' + '=' * 55)
    print('  NEO4J DEMONSTRATION MENU')
    print('=' * 55)
    print('  1. User similarities (coursework centred formula)')
    print('  2. Random items and their reviewers')
    print('  3. Users reviewing multiple categories')
    print('  4. Popular items and shared items')
    print('  5. Exit')
    print('=' * 55)

def main():
    global AVAILABLE_CATEGORIES
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    random.seed(args.seed)
    try:
        AVAILABLE_CATEGORIES = get_categories()
    except Exception as e:
        print(f'[ERROR] Database connection failed: {type(e).__name__}')
        return
    while True:
        show_menu()
        option = input('Select an option: ').strip()
        try:
            if option == '1':
                similarities_option()
            elif option == '2':
                random_items_option()
            elif option == '3':
                multi_category_option()
            elif option == '4':
                popular_items_option()
            elif option == '5':
                print('Leaving the Neo4j menu...')
                break
            else:
                print('Invalid option; enter a number from 1 to 5')
        except Exception as e:
            print(f'Operation failed: {type(e).__name__}')
if __name__ == '__main__':
    main()
