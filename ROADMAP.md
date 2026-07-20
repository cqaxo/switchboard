# Switchboard Roadmap

Each feature is its own branch and PR. Flip the checkbox when the PR merges.

## Day 1: get trustworthy data on disk

- [ ] `feat/ingestion` - minimal pull: fetch a slice from the SODA API, land it raw
- [ ] `feat/incremental-pull` - pagination + `created_date` window for a full-year pull
- [ ] `feat/validation` - quality-check suite and a per-run data quality report

## Day 2: make it smart and observable

- [ ] `feat/enrichment` - predict the responding agency from the complaint text
- [ ] `feat/serving` - load cleaned and enriched rows into DuckDB, small query surface
- [ ] `feat/observability` - freshness, volume, quality pass rates, category drift
