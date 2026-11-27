"""Load settings from environment variables (.env)."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = PROJECT_ROOT / os.getenv("RAW_DATA_DIR", "data/raw")
PROCESSED_DATA_DIR = PROJECT_ROOT / os.getenv("PROCESSED_DATA_DIR", "data/processed")


def pg_params(dbname: str | None = None) -> dict[str, str]:
    """Connection settings for Postgres (for psycopg.connect).

    dbname defaults to POSTGRES_DB (the Day 1 taxi warehouse); pass another name,
    e.g. "olist", to use a different database in the same Postgres server.
    """
    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": os.getenv("POSTGRES_PORT", "5433"),
        "dbname": dbname or os.getenv("POSTGRES_DB", "nyc_taxi"),
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", ""),
    }


def database_url() -> str:
    """Build the SQLAlchemy URL for the Postgres warehouse."""
    p = pg_params()
    return (
        f"postgresql+psycopg://{p['user']}:{p['password']}@{p['host']}:{p['port']}/{p['dbname']}"
    )
