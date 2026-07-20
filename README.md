# Switchboard

A data pipeline for NYC 311 service requests. Switchboard ingests raw
service-request data from the NYC Open Data API, validates and normalizes it,
enriches it by predicting the responding agency from the complaint text, serves
the cleaned data through a query layer, and monitors it for freshness and
category drift.

The name comes from the enrichment step: like a telephone switchboard routing a
call to the right destination, Switchboard routes each 311 request to its likely
responding agency.

## Pipeline stages

1. Ingestion: pull from the Socrata SODA API, land the raw response untouched.
2. Validation and quality: type checks, null checks, temporal sanity,
   categorical normalization, and a per-run data quality report.
3. Enrichment: predict the responding agency from the free-text complaint.
4. Serving: persist cleaned and enriched rows to a queryable store with a small
   dashboard on top.
5. Observability and drift: track freshness, volume, quality pass rates, and
   shifts in the complaint-type distribution over time.

## Status

Project scaffold. Features are built one branch and PR at a time; see
`ROADMAP.md` for the build order and current progress.

## Data source

311 Service Requests from 2020 to Present, NYC Open Data, dataset `erm2-nwe9`.
The data is open and free to use. Requests are read-only.

## Setup

Requires Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/bin/activate        # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

An app token is optional for read-only public pulls (it only raises the rate
limit). To use one, copy the example env file and paste your token:

```bash
cp .env.example .env
# then edit .env and set SOCRATA_APP_TOKEN
```


