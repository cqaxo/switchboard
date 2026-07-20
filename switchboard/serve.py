"""Serving for Switchboard: load clean data and predictions into DuckDB.

Builds a single-file DuckDB database with:
- requests: all cleaned monthly Parquet, as validated (city's data + flags)
- predictions: one row per request, the model's predicted agency, tagged
  with the model file that produced it
- requests_enriched: a view joining the two on unique_key

Predictions live in their own table rather than as a column on requests,
so the validated data stays pristine, retraining only rebuilds the small
table, and prediction sets from different model versions can coexist.
"""

import duckdb
import joblib
import pandas as pd

from switchboard import config

BATCH_SIZE = 500_000


def latest_model_path():
    """Return the most recently saved model file."""
    paths = sorted(config.MODELS_DIR.glob("agency_model_*.joblib"))
    if not paths:
        raise FileNotFoundError(
            "No model found in models/. Run run_enrichment.py first."
        )
    return paths[-1]


def build_requests_table(con):
    """Create the requests table straight from the clean Parquet files."""
    glob = str(config.CLEAN_DIR / "311_*.parquet")
    con.execute("DROP TABLE IF EXISTS requests")
    con.execute(
        f"CREATE TABLE requests AS SELECT * FROM read_parquet('{glob}')"
    )
    count = con.execute("SELECT count(*) FROM requests").fetchone()[0]
    print(f"requests: {count} rows")


def build_predictions_table(con):
    """Predict agency for every request and store in its own table."""
    model_path = latest_model_path()
    model = joblib.load(model_path)
    print(f"predicting with {model_path.name}")

    con.execute("DROP TABLE IF EXISTS predictions")
    con.execute(
        """
        CREATE TABLE predictions (
            unique_key VARCHAR,
            predicted_agency VARCHAR,
            model_file VARCHAR
        )
        """
    )

    offset = 0
    while True:
        batch = con.execute(
            """
            SELECT unique_key,
                   trim(coalesce(complaint_type_norm, '') || ' ' ||
                        coalesce(descriptor_norm, '')) AS text
            FROM requests
            ORDER BY unique_key
            LIMIT ? OFFSET ?
            """,
            [BATCH_SIZE, offset],
        ).df()
        if batch.empty:
            break
        batch["predicted_agency"] = model.predict(batch["text"])
        batch["model_file"] = model_path.name
        con.execute(
            """
            INSERT INTO predictions
            SELECT unique_key, predicted_agency, model_file
            FROM batch
            """
        )
        offset += BATCH_SIZE
        print(f"  predicted through row {offset}")

    count = con.execute("SELECT count(*) FROM predictions").fetchone()[0]
    print(f"predictions: {count} rows")


def build_view(con):
    """Create the joined view queries will use."""
    con.execute("DROP VIEW IF EXISTS requests_enriched")
    con.execute(
        """
        CREATE VIEW requests_enriched AS
        SELECT r.*, p.predicted_agency, p.model_file,
               (r.agency = p.predicted_agency) AS prediction_matches
        FROM requests r
        LEFT JOIN predictions p USING (unique_key)
        """
    )
    print("view requests_enriched created")


def build_database():
    """Build the full serving database."""
    con = duckdb.connect(str(config.DB_PATH))
    try:
        build_requests_table(con)
        build_predictions_table(con)
        build_view(con)
    finally:
        con.close()
    print(f"database written to {config.DB_PATH}")