"""One module per source. Each exposes backfill(conn, cur, since, until) and, where the source
supports it, poll(conn, cur) for the live loop. Both write raw docs and return how many."""
