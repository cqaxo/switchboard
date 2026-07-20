"""Pull the trailing year of NYC 311 requests, one month at a time.

Run from the repo root:
    python pull_year.py

Safe to interrupt and re-run: months that already landed are skipped.
"""

from datetime import datetime, timedelta

from switchboard.ingest import pull_range


def main():
    end = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=365)
    pull_range(start, end)


if __name__ == "__main__":
    main()