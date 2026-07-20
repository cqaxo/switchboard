"""Query the Switchboard database.

Run a canned demo:
    python query.py

Or any SQL directly:
    python query.py "SELECT count(*) FROM requests_enriched"
"""

import sys

import duckdb

from switchboard import config

DEMOS = {
    "monthly volume and month-over-month change": """
        SELECT strftime(created_date, '%Y-%m') AS month,
               count(*) AS complaints,
               count(*) - lag(count(*)) OVER (ORDER BY strftime(created_date, '%Y-%m'))
                   AS change_vs_prev
        FROM requests_enriched
        GROUP BY month ORDER BY month
    """,
    "top complaint types": """
        SELECT complaint_type_norm, count(*) AS n
        FROM requests_enriched
        GROUP BY complaint_type_norm ORDER BY n DESC LIMIT 10
    """,
    "model agreement by actual agency": """
        SELECT agency,
               count(*) AS n,
               round(avg(CASE WHEN prediction_matches THEN 1 ELSE 0 END) * 100, 2)
                   AS pct_match
        FROM requests_enriched
        GROUP BY agency ORDER BY n DESC LIMIT 10
    """,
}


def main():
    con = duckdb.connect(str(config.DB_PATH), read_only=True)
    try:
        if len(sys.argv) > 1:
            print(con.execute(sys.argv[1]).df().to_string(index=False))
            return
        for title, sql in DEMOS.items():
            print(f"\n=== {title} ===")
            print(con.execute(sql).df().to_string(index=False))
    finally:
        con.close()


if __name__ == "__main__":
    main()