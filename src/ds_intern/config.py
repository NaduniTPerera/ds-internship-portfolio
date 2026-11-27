"""Load settings from environment variables (.env)."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = PROJECT_ROOT / os.getenv("RAW_DATA_DIR", "data/raw")
PROCESSED_DATA_DIR = PROJECT_ROOT / os.getenv("PROCESSED_DATA_DIR", "data/processed")


def database_url() -> str:
    """Build the SQLAlchemy URL for the Postgres warehouse."""
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5433")
    db = os.getenv("POSTGRES_DB", "nyc_taxi")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"
