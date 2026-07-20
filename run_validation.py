"""Validate all raw monthly files and print a summary.

Run from the repo root:
    python run_validation.py
"""

from switchboard.validate import run_validation


def main():
    report = run_validation()
    totals = report["totals"]
    print("\nTotals across all files:")
    for key, value in sorted(totals.items()):
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()