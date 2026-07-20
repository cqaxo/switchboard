"""Run a small sample pull and print a quick summary.

Run from the repo root:
    python pull_sample.py
"""

from switchboard.ingest import pull_sample

FIELDS = ["created_date", "agency", "complaint_type", "descriptor", "borough"]


def main():
    records, path = pull_sample(limit=5)
    print(f"Pulled {len(records)} records")
    print(f"Landed raw file at {path}")
    print()
    for i, row in enumerate(records, start=1):
        print(f"Record {i}")
        for field in FIELDS:
            print(f"  {field}: {row.get(field, '<missing>')}")
        print()


if __name__ == "__main__":
    main()