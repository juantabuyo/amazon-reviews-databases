# Database usage

Run commands from the project folder after following the [installation steps](../README.md).
The bundled JSONL fixtures are synthetic. SQLite and client doubles exercise
selected queries and failure paths; **real MySQL, MongoDB and Neo4j integration
has not been checked**. No server versions, throughput or live permissions are
established by those tests.

## Configure three local engines

Use dedicated, disposable stores and accounts limited to them.

| Engine | Default endpoint and store | Configuration |
|---|---|---|
| MySQL | `127.0.0.1:3306`, schema `amazon_reviews_demo` | `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DB` |
| MongoDB | `mongodb://127.0.0.1:27017`, database `amazon_reviews_demo`, collection `reviews_texto` | `MONGO_URI`, `MONGO_DB`; collection name is fixed in `config.py` |
| Neo4j | `bolt://127.0.0.1:7687`, database `amazon-reviews-demo` | `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` |

Only loopback hosts are accepted. MongoDB/Neo4j URIs must select a single host
and must not contain a database path. Store names must use the dedicated demo
prefixes enforced by `config.py`; default databases are rejected. MySQL/MongoDB
names may have lowercase alphanumeric suffixes separated by underscores; Neo4j
uses hyphens.

Provide an installation that supports an existing, named Neo4j database
`amazon-reviews-demo`. The application does not create it and refuses `neo4j`.
MySQL initialisation needs permission to create the schema, tables and indices.
`BATCH_SIZE` defaults to 1,000 and `TOP_N_USERS` to 30.

Copy the example, replace its dummy values with local demonstration credentials
and export them. `.env` is not loaded automatically:

```bash
cp .env.example .env
# Edit .env locally before continuing.
set -a
. ./.env
set +a
```

Keep the completed `.env` private. No real credentials are needed for fixture
validation or the unit tests.

## Initialise a fresh Neo4j Community instance

Choose **one** of the following options for a new instance dedicated to this demo.
Community Edition has one standard database, so name that initial database
`amazon-reviews-demo` rather than trying to add a second one. See the official
[database administration guide](https://neo4j.com/docs/operations-manual/current/database-administration/).

**Set the name before the first DBMS startup, with a fresh data directory or
volume.** The setting does not rename an existing database, and changing it after
initialisation has no effect. Reusing a previously initialised data volume does
not make an instance new. Keep existing databases untouched and use separate
storage for this demo. This follows the documented
[`initial.dbms.default_database` setting](https://neo4j.com/docs/operations-manual/current/configuration/configuration-settings/#config_initial.dbms.default_database).

### Native installation

Install a separate Neo4j Community distribution and its required Java runtime,
following the [installation guide](https://neo4j.com/docs/operations-manual/current/installation/linux/tarball/).
Before starting it, edit its own `conf/neo4j.conf` (not a project file). Use a
new, uninitialised data directory and set:

```ini
initial.dbms.default_database=amazon-reviews-demo
server.default_listen_address=127.0.0.1
```

For an extracted Linux distribution, run these commands from the Neo4j installation
folder, with the real demonstration password already exported as `NEO4J_PASSWORD`:

```bash
: "${NEO4J_PASSWORD:?Export a local demonstration password first}"
bin/neo4j-admin dbms set-initial-password "$NEO4J_PASSWORD"
bin/neo4j console
```

The [initial-password command](https://neo4j.com/docs/operations-manual/current/configuration/set-initial-password/)
is also a first-start operation. Keep the project's `NEO4J_USER=neo4j`,
`NEO4J_DATABASE=amazon-reviews-demo` and `NEO4J_URI=bolt://127.0.0.1:7687`.

### Docker alternative

With Docker installed and running, use an unused container name and free host
ports. Run this once for the new instance, after exporting the demonstration
password above. The volume command allocates a fresh volume instead of reusing
an existing store:

```bash
: "${NEO4J_PASSWORD:?Export a local demonstration password first}"
demo_neo4j_volume="$(docker volume create)"
export NEO4J_AUTH="neo4j/${NEO4J_PASSWORD}"
docker run --detach --name amazon-reviews-demo \
  --publish 127.0.0.1:7474:7474 \
  --publish 127.0.0.1:7687:7687 \
  --volume "${demo_neo4j_volume}:/data" \
  --env NEO4J_AUTH \
  --env NEO4J_initial_dbms_default__database=amazon-reviews-demo \
  neo4j:2026.09.0
unset NEO4J_AUTH
```

The official [Docker settings table](https://neo4j.com/docs/operations-manual/current/docker/ref-settings/)
maps `initial.dbms.default_database` to
`NEO4J_initial_dbms_default__database`. The [Docker guide](https://neo4j.com/docs/operations-manual/current/docker/introduction/)
identifies the versioned image without an `-enterprise` suffix as Community and
explains `NEO4J_AUTH` and `/data` persistence. The tag above is an explicit example,
not a server version tested with this project. Authentication remains enabled;
the published ports are limited to the host's loopback interface. Record the
volume name if you need to retain its data. Restart the same container for later
sessions; do not rerun initialisation to change its database name or password.

After startup, check the database list and a connection to the intended database.
For Docker, the following commands prompt for the password:

```bash
docker exec -it amazon-reviews-demo cypher-shell -u neo4j -d system "SHOW DATABASES;"
docker exec -it amazon-reviews-demo cypher-shell -u neo4j -d amazon-reviews-demo "RETURN 1 AS connected;"
```

For a native installation, use `bin/cypher-shell` with the same arguments after
`cypher-shell`. The [shell documentation](https://neo4j.com/docs/operations-manual/current/cypher-shell/)
describes `-d` for selecting the database. Confirm that `amazon-reviews-demo` is
online before running the project's graph commands.

These instructions have been checked against the official documentation but
**have not been executed as a live integration**. The application still requires
loopback endpoints and dedicated demo names, rejects `neo4j`, and does not create
or rename databases. The explicit destructive-reset warnings below still apply.

## Validate, initialise and load

```bash
python load_data.py validate --file data/synthetic_books.jsonl --category demo_books
python load_data.py validate --file data/synthetic_sports.jsonl --category demo_sports
python load_data.py init
python load_data.py load --file data/synthetic_books.jsonl --category demo_books --report books_load_report.json
python load_data.py load --file data/synthetic_sports.jsonl --category demo_sports --report sports_load_report.json
python visualisations.py
python popularity_recommendations.py
python graph_analysis.py --seed 42
```

Validation does not contact services. `init` creates missing objects without
dropping existing data. Loading refuses a category already present. Categories
come from review events, so a new category can contain items seen previously.
An item's stored category remains its first category. The menus offer seven
visualisations and four alternative graph models. A graph model requires an
empty graph and never clears it automatically.

## Events, ratings and similarity

Rows are review events. Repeated reviewer/item pairs are retained; the schema has
no reliable event identifier for automatic deduplication. Popularity counts
review records, so duplicated source records can affect it. An unreviewed item
is not necessarily unpurchased.

Graph queries aggregate each reviewer/item pair to its mean non-null rating.
The timestamp is the latest known time among the rated events; it is metadata,
not a claim that the mean was the latest rating. Fixture ratings 5 and 3 become
4.0 regardless of order. Shared-item relations use distinct users and item sets.

Similarity retains the coursework formula: each user's mean uses **all** their
aggregated item ratings, while the numerator and both squared-deviation sums
use only shared items. This is not Pearson recalculated on co-rated items alone.
Missing intersections and zero denominators create no edge. Similarity is stored
in both directions, so neighbour counts use distinct neighbours.

## Interpret a failed load

MySQL and MongoDB **do not share a transaction**. The loader validates IDs before
queuing records, stops at the first failed batch and reports engine states
separately. A MongoDB failure may leave part of a document batch while SQL rolls
back. If SQL commit acknowledgement fails, SQL status remains **unknown**, even
when a later rollback succeeds. Earlier completed batches remain.

There is no automatic retry or cross-engine rollback. Inspect the report before
recovery. MongoDB `_load_id` and `_batch_number` track batches, not people. A
successful report compares category counts between stores; equal counts do not
prove field equality or distributed atomicity. The loader assumes a single writer.
Failed graph construction may leave a partial graph and is not reported as success.

## Explicit reset and recovery

**The following commands delete demonstration data.** They are only for the
dedicated stores configured above. Reset boundaries have been tested with doubles,
not real services. Preserve any needed data and inspect the failed report first.

```bash
python reset_demo.py --stores storage --confirm RESET-LOCAL-DEMO
python load_data.py init
python load_data.py load --file data/synthetic_books.jsonl --category demo_books --report books_load_report.json
python load_data.py load --file data/synthetic_sports.jsonl --category demo_sports --report sports_load_report.json
```

Storage reset selects the configured MySQL schema and drops its three project
tables, and resets the exact configured MongoDB collection. To discard a partial
graph before choosing another view:

```bash
python reset_demo.py --stores graph --confirm RESET-LOCAL-DEMO
python graph_analysis.py --seed 42
```

Graph reset names the dedicated Neo4j database explicitly. Reset is itself **not
atomic across engines**; schema changes may commit separately from data writes.
Inspect any reset failure before proceeding. Recovery here is an explicit reset
and reload of permitted inputs, not silent repair of an uncertain partial load.
