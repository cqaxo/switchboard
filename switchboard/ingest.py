"""Minimal ingestion for Switchboard.

Pulls a slice of NYC 311 service requests from the Socrata SODA API and
lands the raw response on disk without modifying it. The raw layer is
immutable: later stages always work from an untouched copy of what the
API returned, which makes every downstream step re-runnable.
"""

import json
import time
from datetime import datetime, timedelta, timezone

import requests

from switchboard import config


def fetch_records(limit=5, offset=0, where=None, select=None, order="created_date DESC"):
    """Fetch a page of records from the 311 dataset."""
    params = {"$limit": limit, "$offset": offset, "$order": order}
    if where:
        params["$where"] = where
    if select:
        params["$select"] = select
    
    headers = {}
    token = config.get_app_token()
    if token:
        headers["X-App-Token"] = token

    response = requests.get(
        config.DATASET_ENDPOINT,
        params=params,
        headers=headers,
        timeout=60,
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


# Columns the pipeline actually uses. Requesting a subset shrinks the pull;
# we still land exactly what the API returns, untouched.
COLUMNS = ",".join([
    "unique_key", "created_date", "closed_date", "agency",
    "complaint_type", "descriptor", "borough", "incident_zip",
    "city", "status", "latitude", "longitude",
])


PAGE_SIZE = 50000


def month_windows(start, end):
    """Yield (window_start, window_end) month pairs covering [start, end)."""
    current = start.replace(day=1)
    while current < end:
        if current.month == 12:
            nxt = current.replace(year=current.year + 1, month=1)
        else:
            nxt = current.replace(month=current.month + 1)
        yield max(current, start), min(nxt, end)
        current = nxt


def pull_window(window_start, window_end, page_size=PAGE_SIZE):
    """Pull every record in [window_start, window_end) via offset pagination."""
    where = (
        f"created_date >= '{window_start:%Y-%m-%dT%H:%M:%S}' "
        f"AND created_date < '{window_end:%Y-%m-%dT%H:%M:%S}'"
    )
    records = []
    offset = 0
    while True:
        page = fetch_records(
            limit=page_size,
            offset=offset,
            where=where,
            select=COLUMNS,
            order="unique_key",
        )
        records.extend(page)
        print(f"    page at offset {offset}: {len(page)} rows")
        if len(page) < page_size:
            return records
        offset += page_size
        time.sleep(0.5)


def pull_range(start, end):
    """Pull [start, end) one month at a time, landing each month raw."""
    for window_start, window_end in month_windows(start, end):
        prefix = f"311_{window_start:%Y%m}"
        existing = list(config.RAW_DIR.glob(f"{prefix}_*.json"))
        if existing:
            print(f"{prefix}: already landed ({existing[0].name}), skipping")
            continue
        print(f"{prefix}: pulling {window_start:%Y-%m-%d} to {window_end:%Y-%m-%d}")
        records = pull_window(window_start, window_end)
        path = land_raw(records, prefix=prefix)
        print(f"{prefix}: landed {len(records)} rows at {path.name}")


def pull_sample(limit=5):
    """Pull a small recent slice and land it. Returns (records, path)."""
    records = fetch_records(limit=limit)
    path = land_raw(records)
    return records, path