"""Load the 9 Olist CSV files into the `olist` Postgres database.

Reuses the Day 1 loading code (ds_intern.db: connect, run_sql_file, copy_arrow
with Postgres COPY) instead of writing a second loader.

Idempotent: the whole load is ONE transaction that truncates all 9 tables and
re-copies them in foreign-key order. Re-running gives the same result; if anything
fails, the transaction rolls back and the previous data stays.

All CSV columns are read as TEXT and Postgres casts them to the types in
sql/olist/001_schema.sql, so values like zip "01037" keep their leading zero and
any malformed value is rejected by the database.

Usage:
    uv run python -m olist.load
"""

import argparse
import csv
import logging
import sys
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pacsv

from ds_intern import db
from ds_intern.config import PROJECT_ROOT, RAW_DATA_DIR

logger = logging.getLogger(__name__)

DBNAME = "olist"
OLIST_DIR = RAW_DATA_DIR / "olist"
SCHEMA_SQL = PROJECT_ROOT / "sql" / "olist" / "001_schema.sql"

# table -> source file, in foreign-key order (parents before children)
TABLES = {
    "category_translation": "product_category_name_translation.csv",
    "customers": "olist_customers_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
}


def read_csv_as_text(path: Path) -> pa.Table:
    """Read a CSV with every column as string; empty fields become NULL.

    newlines_in_values: review messages contain line breaks inside quotes.
    """
    # "utf-8-sig" removes a UTF-8 byte-order mark (the translation file has one)
    # BEFORE the csv module parses quotes, so '﻿"name"' is read as 'name'.
    with open(path, encoding="utf-8-sig", newline="") as f:
        header = next(csv.reader(f))
    return pacsv.read_csv(
        path,
        read_options=pacsv.ReadOptions(column_names=header, skip_rows=1),
        parse_options=pacsv.ParseOptions(newlines_in_values=True),
        convert_options=pacsv.ConvertOptions(
            column_types={name: pa.string() for name in header},
            strings_can_be_null=True,
            quoted_strings_can_be_null=True,
        ),
    )


def load_all(olist_dir: Path = OLIST_DIR) -> dict[str, int]:
    """Create the database/tables if needed, then reload all 9 tables in one transaction."""
    missing = [f for f in TABLES.values() if not (olist_dir / f).exists()]
    if missing:
        raise FileNotFoundError(f"Missing in {olist_dir}: {missing}")

    db.ensure_database(DBNAME)
    counts: dict[str, int] = {}
    with db.connect(DBNAME) as conn:
        db.run_sql_file(conn, SCHEMA_SQL)
        with conn.transaction(), conn.cursor() as cur:
            cur.execute("TRUNCATE " + ", ".join(TABLES) + " RESTART IDENTITY")
            for table, filename in TABLES.items():
                started = time.perf_counter()
                data = read_csv_as_text(olist_dir / filename)
                counts[table] = db.copy_arrow(cur, table, data)
                logger.info("%-22s %9d rows  (%.1f s)", table, counts[table],
                            time.perf_counter() - started)
        conn.execute("ANALYZE")   # fresh statistics for the query planner
    return counts


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description="Load the Olist CSV files into Postgres.").parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    try:
        counts = load_all()
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 2
    logger.info("Done: %d tables, %d rows in total", len(counts), sum(counts.values()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
