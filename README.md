# Amazon review databases

We compare relational, document and graph representations of review data in a
two-student databases project. It loads structured fields into MySQL and review
text into MongoDB, offers seven visualisations and builds four alternative
Neo4j graphs. A popularity
query recommends products a user has not reviewed, ranked by review count, mean
rating and product ID. It is an aggregation baseline, not a trained recommender;
an unreviewed product is not necessarily unpurchased.

![Rating distribution produced by the existing plotting code from the twelve-event synthetic fixture](docs/images/synthetic-ratings.png)

*Saved fixture preview from the current project: 12 synthetic review events,
including 11 ratings and one missing rating. The existing loader and rating
plot use SQLite and a MongoDB double in place of servers. This does not
demonstrate a live MySQL/MongoDB connection.*

## Try it without databases

Tested with Python 3.12.2 on macOS and Python 3.12.14, using pip 26.2.2.
From this folder:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python load_data.py validate --file data/synthetic_books.jsonl --category demo_books
python load_data.py validate --file data/synthetic_sports.jsonl --category demo_sports
python -m unittest discover -s tests -v
```

On Windows, activate with `.venv\Scripts\activate`. These checks do not contact
services. The [fixtures](data/README.md) are **entirely synthetic**: nine book
events and three sports events, involving three fictitious reviewers and six
items. They include repeated ratings and a missing rating. The two validation commands
print:

```text
{"status": "validated_locally", "reviews": 9}
{"status": "validated_locally", "reviews": 3}
```

These counts confirm local input validation; they do not mean records were
written to a server. The project's annotated preview is generated with:

```bash
python preview.py
```

It calls the existing loader and `visualisations.rating_histogram`, using the
same isolated adapters as the tests. It replaces
`docs/images/synthetic-ratings.png` and prints the fixture counts. To save a
separate rendering of the original rating view, without replacing that preview:

```bash
python scripts/make_figures.py --output demo-output/synthetic-rating-distribution.png
```

This separate-output command also ran successfully on macOS with Python 3.12.2.
The [saved separate-output histogram](docs/images/synthetic-rating-distribution.png)
shows two ratings of 2, two of 3, three of 4 and four of 5. The missing
rating is excluded from the plot.

## Run with local services

**Real MySQL, MongoDB and Neo4j integration remains unverified.** Provide disposable
MySQL and MongoDB stores named `amazon_reviews_demo`, plus an existing Neo4j
database named `amazon-reviews-demo`. The application does not create that Neo4j
database and rejects the default `neo4j` name. Provision an installation supporting
the dedicated name. No server versions have been tested.

Use accounts limited to these stores. [Database usage](docs/database-usage.md)
provides environment variables, initialisation and loading commands, and recovery
steps. Copy the fictitious values in `.env.example` into a private `.env`, replace
them with your local credentials, then export them; the application does not load
`.env` automatically. Connections accept loopback endpoints only.

`load_data.py init` creates missing objects without dropping data. Loading refuses
categories already present. Each graph model requires an empty graph and does
not clear it automatically. The usage guide includes explicit reset commands
that **delete demonstration data**.

## Methods and source layout

| Part | Implementation |
|---|---|
| Validation and loading | `load_data.py`: JSONL validation, batched inserts and per-engine failure reporting; `schema.sql`: users, items and review events |
| Popularity baseline | `popularity_recommendations.py`: SQL aggregation with an exclusion subquery for products already reviewed |
| Four graph models | `graph_analysis.py`: centred user similarity, sampled items and reviewers, users across categories, and shared popular items |
| Seven data views | `visualisations.py`: SQL/MongoDB queries and Matplotlib plots, with wordcloud for summary text |
| Offline previews | `preview.py`: annotated saved preview; `scripts/make_figures.py`: separate-output rendering of the original view |
| Explicit service connections | `config.py` and `database_connections.py`: local endpoints and dedicated demo names |

We implement the data mapping, query logic, graph construction and coursework
similarity calculation. The database engines execute SQL/Cypher and store the
data; their Python clients provide the connections. Matplotlib and wordcloud
handle rendering.

## Results and limits

Local checks produced 3 users, 6 items and 12 review events in SQLite, alongside
12 documents in a MongoDB double. These are fixture results, not successful
MySQL/MongoDB integration or throughput measurements. Graph doubles do not
validate Cypher against Neo4j.

Reviews remain events, including repeated user/item pairs. Recommendation
categories come from review rows. Graph ratings average each pair's non-null
ratings; similarity centres users on all their aggregated item ratings, rather
than recomputing Pearson means only on shared items.

MySQL and MongoDB have **no shared transaction**. Failures may leave partial or
uncertain writes and retain earlier batches. Inspect the report before recovery;
there is no automatic retry. [Database usage](docs/database-usage.md) explains
engine configuration, aggregation conventions, failure reports and the explicit,
**destructive** demo reset. Real datasets are not included.

## Tests and version notes

All 20 tests passed in both tested Python environments. The test command above
covers validation, partial loads,
uncertain commits, category reuse, resource cleanup, resets, rating aggregation,
neighbour counts, popularity queries and all seven plots. SQL checks use SQLite
with adapted placeholders; graph and document clients are doubles. They do not
validate server permissions, MySQL DDL/collation, wire protocols or Cypher.

`tests/test_cursor_cleanup.py` adds two tests, with doubles, that every cursor opened
by the seven query functions in `graph_analysis.py` is closed both after a normal
return and after a failed query. With the 20 tests above, all 22 passed on Python
3.12.2 on macOS. If closing a cursor itself raised an error, that error would replace
the query error; this is not covered.

Post-submission corrections replaced embedded credentials, made resets explicit
and improved failure reporting. They also fixed category discovery for reused
products and resource cleanup after a failed query, while retaining review
events, the schema and the coursework similarity formula.

## Academic context and credits

A two-student team project for the Databases course, iMAT, ICAI,
Universidad Pontificia Comillas. The project uses the
MySQL, MongoDB and Neo4j Python clients;
Matplotlib and wordcloud support the plots.
