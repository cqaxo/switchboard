"""Minimal ingestion for Switchboard.

Pulls a slice of NYC 311 service requests from the Socrata SODA API and
lands the raw response on disk without modifying it. The raw layer is
immutable: later stages always work from an untouched copy of what the
API returned, which makes every downstream step re-runnable.
"""

import json
from datetime import datetime, timezone

import requests

from switchboard import config


def fetch_records(limit=5):
    """Fetch the most recent `limit` records from the 311 dataset."""
    params = {
        "$limit": limit,
        "$order": "created_date DESC",
    }

    headers = {}
    token = config.get_app_token()
    if token:
        headers["X-App-Token"] = token

    response = requests.get(
        config.DATASET_ENDPOINT,
        params=params,
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def land_raw(records, prefix="311_sample"):
    """Write records to the raw layer as a timestamped JSON file."""
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = config.RAW_DIR / f"{prefix}_{stamp}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
    return path


def pull_sample(limit=5):
    """Pull a small recent slice and land it. Returns (records, path)."""
    records = fetch_records(limit=limit)
    path = land_raw(records)
    return records, path