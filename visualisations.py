"""Seven review-data views from the university database project.

The original Spanish database fields are retained as schema contracts.
"""

from contextlib import closing

import matplotlib.pyplot as plt

from database_connections import connect_mysql, connect_mongo


AVAILABLE_CATEGORIES = []


def query_rows(sql, parameters=()):
    """Read rows and release the cursor and connection, including on failure."""
    with closing(connect_mysql()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, parameters)
            return cursor.fetchall()


def get_categories():
    return [
        row[0]
        for row in query_rows(
            "SELECT DISTINCT categoria FROM reviews ORDER BY categoria"
        )
    ]


def choose_category(allow_all=True):
    """Return a category or None for an unfiltered view."""
    if not AVAILABLE_CATEGORIES:
        raise ValueError("No categories are available in the database.")
    print("\nAvailable categories:")
    for index, category in enumerate(AVAILABLE_CATEGORIES, 1):
        print(f"  {index}. {category}")
    if allow_all:
        print(f"  {len(AVAILABLE_CATEGORIES) + 1}. All categories")

    while True:
        try:
            choice = int(input("Select an option: "))
            if 1 <= choice <= len(AVAILABLE_CATEGORIES):
                return AVAILABLE_CATEGORIES[choice - 1]
            if allow_all and choice == len(AVAILABLE_CATEGORIES) + 1:
                return None
            print("Invalid option.")
        except ValueError:
            print("Enter a valid number.")


def reviews_by_year():
    category = choose_category(allow_all=True)
    if category:
        rows = query_rows(
            """
            SELECT YEAR(reviewTime) AS review_year, COUNT(*) AS total
            FROM reviews
            WHERE categoria = %s AND reviewTime IS NOT NULL
            GROUP BY review_year
            ORDER BY review_year
            """,
            (category,),
        )
        title = f"Reviews by year — {category}"
    else:
        rows = query_rows(
            """
            SELECT YEAR(reviewTime) AS review_year, COUNT(*) AS total
            FROM reviews
            WHERE reviewTime IS NOT NULL
            GROUP BY review_year
            ORDER BY review_year
            """
        )
        title = "Reviews by year — all products"
    if not rows:
        print("No data found.")
        return

    years = [row[0] for row in rows]
    totals = [row[1] for row in rows]
    plt.figure(figsize=(10, 6))
    plt.bar(years, totals, color="steelblue")
    plt.xlabel("Year")
    plt.ylabel("Number of reviews")
    plt.title(title)
    plt.xticks(years, rotation=45)
    plt.tight_layout()
    plt.show()


def product_popularity():
    """Plot products ranked by review count; this is not a time series."""
    category = choose_category(allow_all=True)
    if category:
        rows = query_rows(
            """
            SELECT asin, COUNT(*) AS total
            FROM reviews
            WHERE categoria = %s
            GROUP BY asin
            ORDER BY total DESC
            """,
            (category,),
        )
        title = f"Product popularity — {category}"
    else:
        rows = query_rows(
            """
            SELECT asin, COUNT(*) AS total
            FROM reviews
            GROUP BY asin
            ORDER BY total DESC
            """
        )
        title = "Product popularity — all products"
    if not rows:
        print("No data found.")
        return

    counts = [row[1] for row in rows]
    plt.figure(figsize=(10, 6))
    plt.plot(range(1, len(counts) + 1), counts, color="steelblue", linewidth=0.8)
    plt.xlabel("Product rank by review count")
    plt.ylabel("Number of reviews")
    plt.title(title)
    plt.tight_layout()
    plt.show()


def rating_histogram():
    """Count reviews by rating, excluding missing ratings from the plot."""
    print("\nFilter by category or individual product?")
    print("  1. Category (or all categories)")
    print("  2. Individual product (asin)")
    choice = input("Select an option: ").strip()

    if choice == "2":
        asin = input("Enter the product asin: ").strip()
        if query_rows("SELECT COUNT(*) FROM articulos WHERE asin = %s", (asin,))[0][0] == 0:
            print("The product does not exist in the database.")
            return
        rows = query_rows(
            """
            SELECT overall, COUNT(*) AS total
            FROM reviews
            WHERE asin = %s
            GROUP BY overall
            ORDER BY overall
            """,
            (asin,),
        )
        title = f"Reviews by rating — product {asin}"
    else:
        category = choose_category(allow_all=True)
        if category:
            rows = query_rows(
                """
                SELECT overall, COUNT(*) AS total
                FROM reviews
                WHERE categoria = %s
                GROUP BY overall
                ORDER BY overall
                """,
                (category,),
            )
            title = f"Reviews by rating — {category}"
        else:
            rows = query_rows(
                """
                SELECT overall, COUNT(*) AS total
                FROM reviews
                GROUP BY overall
                ORDER BY overall
                """
            )
            title = "Reviews by rating — all products"

    # overall permits NULL in the schema; a missing rating has no numeric bin.
    missing_count = sum(row[1] for row in rows if row[0] is None)
    rows = [row for row in rows if row[0] is not None]
    if missing_count:
        print(f"Excluded {missing_count} reviews with missing ratings from this plot.")
    if not rows:
        print("No non-missing ratings found.")
        return
    ratings = [float(row[0]) for row in rows]
    totals = [row[1] for row in rows]
    plt.figure(figsize=(8, 6))
    plt.bar(ratings, totals, color="steelblue", width=0.6)
    plt.xlabel("Rating")
    plt.ylabel("Number of reviews")
    plt.title(title)
    plt.xticks(ratings)
    plt.tight_layout()
    plt.show()


def cumulative_reviews():
    """Show the cumulative review count for each category."""
    plt.figure(figsize=(12, 6))
    for category in AVAILABLE_CATEGORIES:
        rows = query_rows(
            """
            SELECT unixReviewTime
            FROM reviews
            WHERE categoria = %s AND unixReviewTime IS NOT NULL
            ORDER BY unixReviewTime
            """,
            (category,),
        )
        timestamps = [row[0] for row in rows]
        if timestamps:
            counts = list(range(1, len(timestamps) + 1))
            plt.plot(timestamps, counts, label=category, linewidth=1)
    plt.xlabel("Unix timestamp (seconds)")
    plt.ylabel("Cumulative number of reviews")
    plt.title("Reviews over time by category")
    if plt.gca().lines:
        plt.legend()
    plt.tight_layout()
    plt.show()


def reviews_per_reviewer():
    """Count how many reviewers have each number of review records."""
    rows = query_rows(
        """
        SELECT reviews_count, COUNT(*) AS reviewer_count
        FROM (
            SELECT reviewerID, COUNT(*) AS reviews_count
            FROM reviews
            GROUP BY reviewerID
        ) AS sub
        GROUP BY reviews_count
        ORDER BY reviews_count
        """
    )
    if not rows:
        print("No data found.")
        return
    counts = [row[0] for row in rows]
    reviewers = [row[1] for row in rows]
    plt.figure(figsize=(10, 6))
    plt.bar(counts, reviewers, color="steelblue", width=1.0)
    plt.xlabel("Number of reviews")
    plt.ylabel("Number of reviewers")
    plt.title("Review count per reviewer")
    plt.tight_layout()
    plt.show()


def summary_word_cloud():
    """Use summary words longer than three characters from one category."""
    from wordcloud import WordCloud

    category = choose_category(allow_all=False)
    client, collection = connect_mongo()
    words = []
    try:
        documents = collection.find(
            {"categoria": category}, {"summary": 1, "_id": 0}
        )
        for document in documents:
            summary = document.get("summary", "")
            if summary:
                words.extend(word for word in summary.split() if len(word) > 3)
    finally:
        client.close()
    text = " ".join(words)
    if not text.strip():
        print("No summary text found for this category.")
        return
    word_cloud = WordCloud(
        width=800, height=400, background_color="white", max_words=200,
        random_state=0,
    )
    word_cloud.generate(text)
    plt.figure(figsize=(12, 6))
    plt.imshow(word_cloud, interpolation="bilinear")
    plt.axis("off")
    plt.title(f"Summary word cloud — {category}")
    plt.tight_layout()
    plt.show()


def top_reviewers():
    """Retain the original top-15 aggregate without displaying reviewer names."""
    rows = query_rows(
        """
        SELECT u.reviewerName, COUNT(*) AS total
        FROM reviews r
        JOIN usuarios u ON u.reviewerID = r.reviewerID
        WHERE u.reviewerName IS NOT NULL AND u.reviewerName != ''
        GROUP BY r.reviewerID, u.reviewerName
        ORDER BY total DESC
        LIMIT 15
        """
    )
    if not rows:
        print("No data found.")
        return
    # These labels show rank within this plot, not persistent user identifiers.
    labels = [f"Reviewer {rank}" for rank in range(1, len(rows) + 1)]
    totals = [row[1] for row in rows]
    plt.figure(figsize=(10, 7))
    plt.barh(labels[::-1], totals[::-1], color="steelblue")
    plt.xlabel("Number of reviews")
    plt.ylabel("Reviewer (names omitted)")
    plt.title("Top 15 reviewers with a recorded name, by review count")
    plt.tight_layout()
    plt.show()


def show_menu():
    print("\n" + "=" * 55)
    print("  REVIEW DATA VISUALISATIONS")
    print("=" * 55)
    print("  1. Reviews by year")
    print("  2. Product popularity by review count")
    print("  3. Rating histogram")
    print("  4. Cumulative reviews over time")
    print("  5. Review count per reviewer")
    print("  6. Summary word cloud by category")
    print("  7. Top 15 reviewers (names omitted)")
    print("  8. Exit")
    print("=" * 55)


def main():
    global AVAILABLE_CATEGORIES
    try:
        AVAILABLE_CATEGORIES = get_categories()
    except Exception as error:
        print(f"[ERROR] Unable to read database categories ({type(error).__name__}).")
        return
    actions = {
        "1": reviews_by_year,
        "2": product_popularity,
        "3": rating_histogram,
        "4": cumulative_reviews,
        "5": reviews_per_reviewer,
        "6": summary_word_cloud,
        "7": top_reviewers,
    }
    while True:
        show_menu()
        choice = input("Select an option: ").strip()
        if choice == "8":
            print("Leaving the visualisation menu.")
            break
        if choice not in actions:
            print("Invalid option; enter a number from 1 to 8.")
            continue
        try:
            actions[choice]()
        except Exception as error:
            # Driver errors can contain a connection URI or credentials.
            print(f"[ERROR] Unable to draw this view ({type(error).__name__}).")
        finally:
            plt.close("all")


if __name__ == "__main__":
    main()
