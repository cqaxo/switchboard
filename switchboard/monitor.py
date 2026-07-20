"""Observability for Switchboard: freshness, volume, quality, drift.

Reads the serving database and answers, per run:
- Freshness: how old is the newest record?
- Volume: is the recent daily complaint rate normal vs baseline?
- Quality: are validation flag rates stable vs baseline?
- Drift: which complaint types changed share vs baseline?

Recent window = trailing RECENT_DAYS days of data (by created_date).
Baseline = everything before it.

A complaint type is flagged as drifting only if BOTH thresholds trip:
absolute share change >= DRIFT_ABS_POINTS percentage points AND relative
change >= DRIFT_REL_FRACTION of baseline share. Absolute-only misses
rare-category explosions; relative-only amplifies noise in tiny shares.
"""

import json
from datetime import datetime, timezone

import duckdb

from switchboard import config

RECENT_DAYS = 30
DRIFT_ABS_POINTS = 1.0       # percentage points
DRIFT_REL_FRACTION = 0.25    # fraction of baseline share
VOLUME_ALERT_FRACTION = 0.25 # daily-rate change that triggers an alert
FLAG_COLUMNS = [
    "flag_sentinel_borough",
    "flag_missing_descriptor",
    "flag_missing_coords",
    "flag_closed_before_created",
]


def check_freshness(con):
    """Age of the newest record, in days."""
    newest = con.execute(
        "SELECT max(created_date) FROM requests"
    ).fetchone()[0]
    age_days = (datetime.now() - newest).total_seconds() / 86400
    return {"newest_record": newest.isoformat(), "age_days": round(age_days, 2)}


def window_bounds(con):
    """Compute the recent-window cutoff from the data itself."""
    return con.execute(
        f"SELECT max(created_date) - INTERVAL {RECENT_DAYS} DAY FROM requests"
    ).fetchone()[0]


def check_volume(con, cutoff):
    """Compare recent daily complaint rate to baseline daily rate."""
    recent_rate, base_rate = con.execute(
        """
        SELECT
          count(*) FILTER (WHERE created_date >= ?)
            / ?,
          count(*) FILTER (WHERE created_date < ?)
            / greatest(date_diff('day',
                (SELECT min(created_date) FROM requests), ?), 1)
        FROM requests
        """,
        [cutoff, float(RECENT_DAYS), cutoff, cutoff],
    ).fetchone()
    change = (recent_rate - base_rate) / base_rate if base_rate else 0.0
    return {
        "recent_daily_rate": round(recent_rate),
        "baseline_daily_rate": round(base_rate),
        "change_fraction": round(change, 4),
        "alert": abs(change) >= VOLUME_ALERT_FRACTION,
    }


def check_quality(con, cutoff):
    """Compare validation flag rates, recent vs baseline."""
    out = {}
    for col in FLAG_COLUMNS:
        recent, base = con.execute(
            f"""
            SELECT
              avg(CASE WHEN {col} THEN 1.0 ELSE 0.0 END)
                FILTER (WHERE created_date >= ?),
              avg(CASE WHEN {col} THEN 1.0 ELSE 0.0 END)
                FILTER (WHERE created_date < ?)
            FROM requests
            """,
            [cutoff, cutoff],
        ).fetchone()
        out[col] = {
            "recent_pct": round((recent or 0) * 100, 3),
            "baseline_pct": round((base or 0) * 100, 3),
        }
    return out


def check_drift(con, cutoff):
    """Flag complaint types whose share moved past both thresholds."""
    rows = con.execute(
        """
        WITH recent AS (
          SELECT complaint_type_norm AS ct,
                 count(*) * 100.0 / sum(count(*)) OVER () AS share
          FROM requests WHERE created_date >= ?
          GROUP BY ct
        ),
        baseline AS (
          SELECT complaint_type_norm AS ct,
                 count(*) * 100.0 / sum(count(*)) OVER () AS share
          FROM requests WHERE created_date < ?
          GROUP BY ct
        )
        SELECT coalesce(r.ct, b.ct) AS complaint_type,
               round(coalesce(b.share, 0), 3) AS baseline_share,
               round(coalesce(r.share, 0), 3) AS recent_share
        FROM recent r FULL OUTER JOIN baseline b USING (ct)
        """,
        [cutoff, cutoff],
    ).fetchall()

    drifting = []
    for ct, base_share, recent_share in rows:
        abs_change = recent_share - base_share
        rel_change = abs_change / base_share if base_share else float("inf")
        if (
            abs(abs_change) >= DRIFT_ABS_POINTS
            and abs(rel_change) >= DRIFT_REL_FRACTION
        ):
            drifting.append({
                "complaint_type": ct,
                "baseline_share_pct": base_share,
                "recent_share_pct": recent_share,
                "change_points": round(abs_change, 3),
            })
    drifting.sort(key=lambda d: -abs(d["change_points"]))
    return drifting


def run_monitor():
    """Run all checks and write an observability report."""
    con = duckdb.connect(str(config.DB_PATH), read_only=True)
    try:
        cutoff = window_bounds(con)
        report = {
            "run_at": datetime.now(timezone.utc).isoformat(),
            "recent_window_start": cutoff.isoformat(),
            "freshness": check_freshness(con),
            "volume": check_volume(con, cutoff),
            "quality": check_quality(con, cutoff),
            "drift": check_drift(con, cutoff),
        }
    finally:
        con.close()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = config.REPORTS_DIR / f"observability_{stamp}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    report["report_path"] = str(path)
    return report