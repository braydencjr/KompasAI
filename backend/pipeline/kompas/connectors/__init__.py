"""One module per source. Scheduled streams expose ingest*(run, cur, opts); live ones poll(run, cur).
Every connector writes Documents through the ingestion Run (kompas/ingest.py), never to the database directly."""
