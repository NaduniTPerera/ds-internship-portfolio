"""Read raw monthly taxi files. Shared by all Day 2 quality scripts."""

from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from ds_intern.config import RAW_DATA_DIR

YEAR = 2024
MONTHS = [date(YEAR, m, 1) for m in range(1, 7)]


def parse_month(value: str) -> date:
    """'2024-03' -> date(2024, 3, 1)."""
    return datetime.strptime(value, "%Y-%m").date()


def month_path(month: date, raw_dir: Path = RAW_DATA_DIR) -> Path:
    return raw_dir / f"yellow_tripdata_{month:%Y-%m}.parquet"


def load_month(month: date, columns: list[str] | None = None,
               raw_dir: Path = RAW_DATA_DIR) -> pd.DataFrame:
    """Load one raw month as a DataFrame (optionally only some columns).

    Column names are kept exactly as TLC publishes them (e.g. 'VendorID').
    """
    path = month_path(month, raw_dir)
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run: uv run python -m ingest.download")
    return pq.read_table(path, columns=columns).to_pandas()
