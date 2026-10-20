# Knowledge data source

The existing VietStyle document index in Supabase is the source of truth for
knowledge retrieval. The application reads its indexed chunks through the
configured `DATABASE_URL`; this repository does not copy, re-ingest, or maintain
a second local corpus.

Use `evaluation/run_vietstyle_benchmark.py` with the configured Supabase index
to evaluate retrieval. It checks the current VietStyle benchmark cases against
the live index.
