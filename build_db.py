"""Build the DuckDB serving database from clean data and the latest model.

Run from the repo root:
    python build_db.py
"""

from switchboard.serve import build_database


def main():
    build_database()


if __name__ == "__main__":
    main()