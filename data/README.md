# Synthetic review fixtures

`synthetic_books.jsonl` and `synthetic_sports.jsonl` are fictitious fixtures created on 17 October 2026. They contain invented users, item identifiers, summaries and review text. They are not extracted or anonymised Amazon reviews.

There are nine book events and three sports events, three distinct made-up reviewers and six distinct made-up items. The two ratings for `demo-user-1` / `demo-book-a` are 5 and 3: the graph query aggregates them to 4.0 while the storage/popularity queries retain both events. One event has a null rating to exercise missing-value handling.

Original JSON field names are preserved: `reviewerID`, `reviewerName`, `asin`, `overall`, `helpful`, `unixReviewTime`, `reviewTime`, `summary` and `reviewText`. Category is supplied as a loading argument. Valid dates use the original `MM DD, YYYY` format; invalid or missing dates remain SQL NULL, as in the submission.

Real Amazon review files are not included. These fixtures define the expected JSONL schema, not the distributions of a real dataset. For a real-data run, supply an authorised JSONL release with this schema and record its source, version and terms.
