from datetime import date, datetime

import pyarrow as pa

from ingest.load_postgres import COLUMN_MAP, FACT_COLUMNS, next_month, parse_months, transform_batch


def make_batch(pickups: list[datetime]) -> pa.RecordBatch:
    """A small batch with every source column; only pickup times differ."""
    n = len(pickups)
    data = {src: pa.array([1] * n, pa.int64()) for src in COLUMN_MAP}
    data["tpep_pickup_datetime"] = pa.array(pickups, pa.timestamp("us"))
    data["tpep_dropoff_datetime"] = pa.array(pickups, pa.timestamp("us"))
    data["store_and_fwd_flag"] = pa.array(["N"] * n)
    return pa.RecordBatch.from_pydict(data)


def test_rows_outside_month_are_dropped():
    batch = make_batch([
        datetime(2024, 3, 1, 0, 0),     # first second of March -> keep
        datetime(2024, 3, 31, 23, 59),  # end of March -> keep
        datetime(2024, 2, 29, 23, 59),  # February -> drop
        datetime(2024, 4, 1, 0, 0),     # April -> drop
        datetime(2009, 1, 1, 0, 0),     # bad year -> drop
    ])
    clean, dropped = transform_batch(batch, date(2024, 3, 1))
    assert clean.num_rows == 2
    assert dropped == 3


def test_date_key_source_month_and_column_order():
    clean, _ = transform_batch(make_batch([datetime(2024, 3, 15, 8, 30)]), date(2024, 3, 1))
    assert clean.column_names == FACT_COLUMNS
    assert clean["pickup_date_key"].to_pylist() == [20240315]
    assert clean["source_month"].to_pylist() == [date(2024, 3, 1)]


def test_next_month_rolls_over_year():
    assert next_month(date(2024, 12, 1)) == date(2025, 1, 1)


def test_parse_months_default_is_jan_to_jun():
    months = parse_months(None)
    assert months[0] == date(2024, 1, 1) and months[-1] == date(2024, 6, 1)
    assert parse_months(["2024-03"]) == [date(2024, 3, 1)]
