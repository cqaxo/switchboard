"""Validation and quality for Switchboard.

Reads raw monthly files, applies quality checks, and writes a cleaned
Parquet file per month plus a per-run quality report. Raw files are never
modified.

Policy:
- Hard failures (missing unique_key or created_date, duplicate unique_key)
  are dropped, and the drop counts are reported.
- Soft failures (sentinel borough, bad coordinates, temporal anomalies)
  are flagged in boolean columns, not dropped.
- Normalization adds *_norm columns; original values are preserved.
"""

import json
from datetime import datetime, timezone

import pandas as pd

from switchboard import config

# Rough bounding box for NYC. Coordinates outside it are flagged.
LAT_MIN, LAT_MAX = 40.4, 41.0
LON_MIN, LON_MAX = -74.3, -73.6

SENTINELS = {"unspecified", "n/a", "na", "none", ""}


def normalize_text(series):
    """Strip, collapse internal whitespace, and uppercase a text column."""
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
        .str.upper()
    )


def validate_frame(df, seen_keys):
    """Validate one month of records. Returns (clean_df, stats)."""
    stats = {"rows_in": len(df)}

    # --- Hard failures: drop and count ---
    missing_key = df["unique_key"].isna()
    missing_created = df["created_date"].isna()
    stats["dropped_missing_unique_key"] = int(missing_key.sum())
    stats["dropped_missing_created_date"] = int(missing_created.sum())
    df = df[~missing_key & ~missing_created].copy()

    dup_within = df["unique_key"].duplicated(keep="first")
    dup_across = df["unique_key"].isin(seen_keys)
    dups = dup_within | dup_across
    stats["dropped_duplicate_unique_key"] = int(dups.sum())
    df = df[~dups].copy()
    seen_keys.update(df["unique_key"])

    # --- Types ---
    df["created_date"] = pd.to_datetime(df["created_date"], errors="coerce")
    df["closed_date"] = pd.to_datetime(df["closed_date"], errors="coerce")
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")

    # A created_date that fails to parse is also a hard failure.
    unparseable = df["created_date"].isna()
    stats["dropped_unparseable_created_date"] = int(unparseable.sum())
    df = df[~unparseable].copy()

    # --- Normalization: add columns, never overwrite ---
    for col in ["complaint_type", "descriptor", "borough", "city", "status"]:
        if col in df.columns:
            df[f"{col}_norm"] = normalize_text(df[col])

    # --- Soft failures: flag, don't drop ---
    df["flag_sentinel_borough"] = df["borough_norm"].str.lower().isin(SENTINELS)
    df["flag_missing_descriptor"] = df["descriptor_norm"].str.lower().isin(SENTINELS)

    now = pd.Timestamp(datetime.now(timezone.utc)).tz_localize(None)
    df["flag_future_created"] = df["created_date"] > now
    df["flag_closed_before_created"] = (
        df["closed_date"].notna() & (df["closed_date"] < df["created_date"])
    )

    has_coords = df["latitude"].notna() & df["longitude"].notna()
    in_bounds = (
        df["latitude"].between(LAT_MIN, LAT_MAX)
        & df["longitude"].between(LON_MIN, LON_MAX)
    )
    df["flag_missing_coords"] = ~has_coords
    df["flag_out_of_bounds_coords"] = has_coords & ~in_bounds

    # --- Stats for the report ---
    stats["rows_out"] = len(df)
    for col in df.columns:
        if col.startswith("flag_"):
            stats[col] = int(df[col].sum())
    stats["pct_null_closed_date"] = round(
        float(df["closed_date"].isna().mean()) * 100, 2
    )
    return df, stats


def run_validation():
    """Validate every raw monthly file. Writes clean Parquet and a report."""
    config.CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    raw_files = sorted(config.RAW_DIR.glob("311_2*.json"))
    seen_keys = set()
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "files": {},
    }

    for path in raw_files:
        month = path.name.split("_")[1]  # e.g. 202508
        df = pd.read_json(path, dtype={"unique_key": str, "incident_zip": str})
        clean, stats = validate_frame(df, seen_keys)
        out_path = config.CLEAN_DIR / f"311_{month}.parquet"
        clean.to_parquet(out_path, index=False)
        report["files"][path.name] = stats
        print(
            f"{path.name}: {stats['rows_in']} in, {stats['rows_out']} out, "
            f"{stats['rows_in'] - stats['rows_out']} dropped"
        )

    totals = {}
    for stats in report["files"].values():
        for key, value in stats.items():
            if isinstance(value, (int, float)) and not key.startswith("pct_"):
                totals[key] = totals.get(key, 0) + value
    report["totals"] = totals

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = config.REPORTS_DIR / f"quality_{stamp}.json"
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nQuality report written to {report_path}")
    return report