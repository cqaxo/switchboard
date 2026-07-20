"""Enrichment for Switchboard: predict the responding agency from complaint text.

Trains a TF-IDF + logistic regression baseline on cleaned monthly Parquet.
The split is temporal (train on earlier months, test on the most recent)
to mirror deployment: the model only ever sees the past.

Rare agencies (fewer than MIN_AGENCY_ROWS training rows) are collapsed
into OTHER. Metrics reported: accuracy, macro F1, and per-class
precision/recall, because accuracy alone hides minority-class failure
under class imbalance.
"""

import json
from datetime import datetime, timezone

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer

from switchboard import config

TEST_MONTHS = 2          # most recent N months held out for testing
SAMPLE_ROWS = 300_000    # training sample size
MIN_AGENCY_ROWS = 1000   # agencies below this in training collapse to OTHER
RANDOM_STATE = 42


def load_clean():
    """Load all clean monthly Parquet files, tagged with their month."""
    frames = []
    for path in sorted(config.CLEAN_DIR.glob("311_*.parquet")):
        month = path.stem.split("_")[1]
        df = pd.read_parquet(
            path, columns=["complaint_type_norm", "descriptor_norm", "agency"]
        )
        df["month"] = month
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def prepare(df):
    """Build the text feature and drop rows unusable for training."""
    df = df[df["agency"].notna() & (df["agency"] != "")].copy()
    df["text"] = (
        df["complaint_type_norm"].fillna("")
        + " "
        + df["descriptor_norm"].fillna("")
    ).str.strip()
    df = df[df["text"] != ""]
    return df


def temporal_split(df):
    """Hold out the most recent TEST_MONTHS months as the test set."""
    months = sorted(df["month"].unique())
    test_months = months[-TEST_MONTHS:]
    train = df[~df["month"].isin(test_months)]
    test = df[df["month"].isin(test_months)]
    return train, test, test_months


def collapse_rare(train, test):
    """Collapse agencies rare in training into OTHER, in both splits."""
    counts = train["agency"].value_counts()
    keep = set(counts[counts >= MIN_AGENCY_ROWS].index)
    train = train.assign(
        label=train["agency"].where(train["agency"].isin(keep), "OTHER")
    )
    test = test.assign(
        label=test["agency"].where(test["agency"].isin(keep), "OTHER")
    )
    return train, test, sorted(keep)


def train_model(train_texts, train_labels):
    """Fit the TF-IDF + logistic regression pipeline."""
    model = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=5)),
        ("clf", LogisticRegression(max_iter=1000, random_state=RANDOM_STATE)),
    ])
    model.fit(train_texts, train_labels)
    return model


def run_enrichment():
    """Train, evaluate, and persist the agency prediction baseline."""
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    df = prepare(load_clean())
    train, test, test_months = temporal_split(df)
    train, test, kept = collapse_rare(train, test)

    sample = train.sample(
        n=min(SAMPLE_ROWS, len(train)), random_state=RANDOM_STATE
    )
    print(
        f"Training on {len(sample)} of {len(train)} rows; "
        f"testing on {len(test)} rows from months {test_months}"
    )
    print(f"Classes: {len(kept)} agencies kept, rare collapsed to OTHER")

    model = train_model(sample["text"], sample["label"])
    preds = model.predict(test["text"])

    acc = accuracy_score(test["label"], preds)
    macro_f1 = f1_score(test["label"], preds, average="macro")
    per_class = classification_report(
        test["label"], preds, output_dict=True, zero_division=0
    )

    print(f"\nAccuracy: {acc:.4f}")
    print(f"Macro F1: {macro_f1:.4f}")
    print(f"\n{classification_report(test['label'], preds, zero_division=0)}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    model_path = config.MODELS_DIR / f"agency_model_{stamp}.joblib"
    joblib.dump(model, model_path)

    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "train_rows_sampled": int(len(sample)),
        "train_rows_available": int(len(train)),
        "test_rows": int(len(test)),
        "test_months": test_months,
        "classes_kept": kept,
        "accuracy": round(float(acc), 4),
        "macro_f1": round(float(macro_f1), 4),
        "per_class": per_class,
        "model_file": model_path.name,
    }
    report_path = config.REPORTS_DIR / f"enrichment_{stamp}.json"
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nModel saved to {model_path}")
    print(f"Metrics report written to {report_path}")
    return report