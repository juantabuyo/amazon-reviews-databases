"""Recommend popular products not yet reviewed by a selected reviewer.

Popularity is the number of review records, not a trained prediction model.
"""

from database_connections import connect_mysql


def get_categories(connection):
    with connection.cursor() as cursor:
        cursor.execute("SELECT DISTINCT categoria FROM reviews ORDER BY categoria")
        return [row[0] for row in cursor.fetchall()]


def reviewer_exists(connection, reviewer_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM usuarios WHERE reviewerID = %s", (reviewer_id,)
        )
        return cursor.fetchone()[0] > 0


def category_exists(connection, category):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM reviews WHERE categoria = %s", (category,)
        )
        return cursor.fetchone()[0] > 0


def recommend_unreviewed_products(connection, reviewer_id, category, limit=10):
    """Rank unreviewed products by review count, mean rating, then asin.

    Repeated review records contribute to COUNT(*) as in the original query.
    Absence of a review does not establish that a product has never been bought.
    The database column names are retained from the original schema.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        raise ValueError("limit must be a positive integer.")
    sql = """
        SELECT
            r.asin,
            COUNT(*) AS review_count,
            ROUND(AVG(r.overall), 2) AS mean_rating
        FROM reviews r
        WHERE r.categoria = %s
          AND NOT EXISTS (
              SELECT 1
              FROM reviews ru
              WHERE ru.reviewerID = %s
                AND ru.asin = r.asin
          )
        GROUP BY r.asin
        ORDER BY review_count DESC, mean_rating DESC, r.asin ASC
        LIMIT %s
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, (category, reviewer_id, limit))
        return cursor.fetchall()


def choose_category(connection):
    categories = get_categories(connection)
    if not categories:
        raise ValueError("No categories are available in the database.")
    print("\nAvailable categories:")
    for index, category in enumerate(categories, start=1):
        print(f" {index}. {category}")
    while True:
        try:
            choice = int(input("Select a category by number: ").strip())
            if 1 <= choice <= len(categories):
                return categories[choice - 1]
            print("Invalid option.")
        except ValueError:
            print("Enter a valid number.")


def show_recommendations(category, recommendations):
    print("\n" + "=" * 70)
    print("POPULAR PRODUCTS NOT YET REVIEWED BY THE SELECTED REVIEWER")
    print("=" * 70)
    print(f"Category: {category}")
    if not recommendations:
        print("\nNo products to recommend in this category.")
        print("The reviewer may have reviewed every product, or the data may be sparse.")
        return
    for rank, (asin, review_count, mean_rating) in enumerate(recommendations, start=1):
        print(
            f" {rank:2d}. ASIN: {asin} | reviews: {review_count} | "
            f"mean rating: {mean_rating}"
        )


def main():
    connection = None
    print("=" * 70)
    print("POPULAR PRODUCTS NOT YET REVIEWED")
    print("=" * 70)
    try:
        connection = connect_mysql()
        reviewer_id = input("Enter the original reviewerID: ").strip()
        if not reviewer_id:
            print("Enter a non-empty reviewerID.")
            return
        if not reviewer_exists(connection, reviewer_id):
            print("The reviewer does not exist in the database.")
            return
        category = choose_category(connection)
        if not category_exists(connection, category):
            print("The category does not exist in the database.")
            return
        recommendations = recommend_unreviewed_products(connection, reviewer_id, category)
        show_recommendations(category, recommendations)
    except Exception as error:
        print(f"[ERROR] Recommendation query failed ({type(error).__name__}).")
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    main()
