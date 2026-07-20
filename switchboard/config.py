"""Configuration for Switchboard.

Holds the dataset identifiers, the SODA endpoint, filesystem paths, and the
app token loader. The app token is optional for read-only public pulls, it
only raises the Socrata rate limit. Keep the real token in a .env file
(gitignored), never in the repo.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# NYC Open Data (Socrata) dataset: 311 Service Requests from 2020 to Present.
DOMAIN = "data.cityofnewyork.us"
DATASET_ID = "erm2-nwe9"
DATASET_ENDPOINT = f"https://{DOMAIN}/resource/{DATASET_ID}.json"

# Paths. The raw layer is the immutable landing zone for API responses.
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CLEAN_DIR = DATA_DIR / "clean"
REPORTS_DIR = DATA_DIR / "reports"
MODELS_DIR = REPO_ROOT / "models"


def get_app_token():
    """Return the Socrata app token from the environment, or None if unset."""
    return os.getenv("SOCRATA_APP_TOKEN")
