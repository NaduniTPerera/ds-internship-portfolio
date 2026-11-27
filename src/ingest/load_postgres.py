"""Load the NYC taxi files from data/raw into the Postgres star schema.

Usage (from the repo root, after sql/001_schema.sql has been applied):
    uv run python -m ingest.load_postgres                    # all months
    uv run python -m ingest.load_postgres --months 2024-03   # one month

How it works:
1. dim_zone is upserted from taxi_zone_lookup.csv.
2. Each monthly Parquet file is read in batches (default 500,000 rows), so the
   full 20M rows are never in memory at once.
3. Each month is loaded in ONE transaction:
       DELETE that month's rows -> COPY the new rows -> upsert load_batch
   Re-running a month replaces it (no duplicates). If anything fails, the
   transaction rolls back and the previous data stays intact.
4. Rows whose pickup time is outside the file's month are dropped and counted.
"""

import argparse
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import psycopg
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from ds_intern import db
from ds_intern.config import RAW_DATA_DIR

logger = logging.getLogger(__name__)

YEAR = 2024
MONTHS = range(1, 7)
DEFAULT_BATCH_SIZE = 500_000
ZONE_FILE = "taxi_zone_lookup.csv"

# Parquet column name -> fact_trips column name (order = COPY column order)
COLUMN_MAP = {
    "VendorID": "vendor_id",
    "payment_type": "payment_type_id",
    "PULocationID": "pu_location_id",
    "DOLocationID": "do_location_id",
    "tpep_pickup_datetime": "pickup_datetime",
    "tpep_dropoff_datetime": "dropoff_datetime",
    "passenger_count": "passenger_count",
    "trip_distance": "trip_distance",
    "RatecodeID": "rate_code_id",
    "store_and_fwd_flag": "store_and_fwd_flag",
    "fare_amount": "fare_amount",
    "extra": "extra",
    "mta_tax": "mta_tax",
    "tip_amount": "tip_amount",
    "tolls_amount": "tolls_amount",
    "improvement_surcharge": "improvement_surcharge",
    "congestion_surcharge": "congestion_surcharge",
    "Airport_fee": "airport_fee",
    "total_amount": "total_amount",
}
FACT_COLUMNS = [*COLUMN_MAP.values(), "pickup_date_key", "source_month"]


def next_month(month_start: date) -> date:
    if month_start.month == 12:
        return date(month_start.year + 1, 1, 1)
    return date(month_start.year, month_start.month + 1, 1)


def transform_batch(batch: pa.RecordBatch, month_start: date) -> tuple[pa.Table, int]:
    """Rename columns, drop rows outside the month, add date key and source month.

    Returns (clean table in FACT_COLUMNS order, number of dropped rows).
    """
    # Match source columns case-insensitively (TLC has changed the casing over time).
    by_lower = {name.lower(): name for name in batch.schema.names}
    table = pa.table({dst: batch.column(by_lower[src.lower()]) for src, dst in COLUMN_MAP.items()})

    start = pa.scalar(datetime.combine(month_start, datetime.min.time()), pa.timestamp("us"))
    end = pa.scalar(datetime.combine(next_month(month_start), datetime.min.time()),
                    pa.timestamp("us"))
    pickup = table["pickup_datetime"]
    in_month = pc.and_(pc.greater_equal(pickup, start), pc.less(pickup, end))
    clean = table.filter(in_month)
    dropped = table.num_rows - clean.num_rows

    # pickup_date_key = YYYYMMDD as an integer, e.g. 20240115
    pickup = clean["pickup_datetime"]
    date_key = pc.add(
        pc.add(pc.multiply(pc.year(pickup), 10_000), pc.multiply(pc.month(pickup), 100)),
        pc.day(pickup),
    ).cast(pa.int32())
    clean = clean.append_column("pickup_date_key", date_key)
    clean = clean.append_column(
        "source_month", pa.repeat(pa.scalar(month_start, pa.date32()), clean.num_rows)
    )
    return clean, dropped


def load_zones(conn: psycopg.Connection, path: Path) -> int:
    """Upsert dim_zone from the zone lookup CSV (265 rows)."""
    zones = pd.read_csv(path).astype(object)
    zones = zones.where(zones.notna(), None)
    rows = list(zones[["LocationID", "Borough", "Zone", "service_zone"]].itertuples(index=False))
    with conn.transaction(), conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO dim_zone (location_id, borough, zone, service_zone)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (location_id) DO UPDATE
               SET borough = EXCLUDED.borough,
                   zone = EXCLUDED.zone,
                   service_zone = EXCLUDED.service_zone
            """,
            rows,
        )
    logger.info("dim_zone: upserted %d zones", len(rows))
    return len(rows)


def load_month(conn: psycopg.Connection, path: Path, month_start: date, batch_size: int) -> int:
    """Replace one month in fact_trips. Returns the number of rows loaded."""
    started = time.perf_counter()
    loaded = dropped = 0
    parquet = pq.ParquetFile(path)

    with conn.transaction(), conn.cursor() as cur:
        cur.execute("DELETE FROM fact_trips WHERE source_month = %s", (month_start,))
        if cur.rowcount:
            logger.info("%s: deleted %d existing rows (reload)", month_start, cur.rowcount)

        for i, batch in enumerate(parquet.iter_batches(batch_size=batch_size), start=1):
            clean, n_dropped = transform_batch(batch, month_start)
            db.copy_arrow(cur, "fact_trips", clean, FACT_COLUMNS)
            loaded += clean.num_rows
            dropped += n_dropped
            logger.info("%s: batch %d copied (%d rows so far)", month_start, i, loaded)

        cur.execute(
            """
            INSERT INTO load_batch (source_month, source_file, rows_loaded, rows_dropped)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (source_month) DO UPDATE
               SET source_file = EXCLUDED.source_file,
                   rows_loaded = EXCLUDED.rows_loaded,
                   rows_dropped = EXCLUDED.rows_dropped,
                   loaded_at = now()
            """,
            (month_start, path.name, loaded, dropped),
        )

    logger.info(
        "%s: loaded %d rows, dropped %d (pickup outside month) in %.0f s",
        month_start, loaded, dropped, time.perf_counter() - started,
    )
    return loaded


def parse_months(values: list[str] | None) -> list[date]:
    if not values:
        return [date(YEAR, m, 1) for m in MONTHS]
    return [datetime.strptime(v, "%Y-%m").date() for v in values]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load NYC taxi data into Postgres.")
    parser.add_argument("--months", nargs="+", metavar="YYYY-MM",
                        help="months to load (default: 2024-01 to 2024-06)")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    months = parse_months(args.months)
    files = {m: RAW_DATA_DIR / f"yellow_tripdata_{m:%Y-%m}.parquet" for m in months}
    missing = [p.name for p in [RAW_DATA_DIR / ZONE_FILE, *files.values()] if not p.exists()]
    if missing:
        logger.error("Missing files in %s: %s. Run ingest.download first.", RAW_DATA_DIR, missing)
        return 1

    with db.connect() as conn:
        load_zones(conn, RAW_DATA_DIR / ZONE_FILE)
        total = sum(load_month(conn, files[m], m, args.batch_size) for m in months)

        # Refresh planner statistics and clean up rows deleted by reloads.
        logger.info("Running VACUUM ANALYZE on fact_trips")
        conn.execute("VACUUM ANALYZE fact_trips")

    logger.info("Done: %d rows loaded for %d month(s)", total, len(months))
    return 0


if __name__ == "__main__":
    sys.exit(main())
