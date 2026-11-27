"""Shared helpers for tests: build tiny hand-made taxi DataFrames."""

import pandas as pd

# One trip that passes every validation rule (January 2024, credit card, Manhattan).
VALID_TRIP = {
    "VendorID": 2,
    "tpep_pickup_datetime": pd.Timestamp("2024-01-15 08:00:00"),
    "tpep_dropoff_datetime": pd.Timestamp("2024-01-15 08:20:00"),
    "passenger_count": 1.0,
    "trip_distance": 3.0,
    "RatecodeID": 1.0,
    "store_and_fwd_flag": "N",
    "PULocationID": 161,
    "DOLocationID": 236,
    "payment_type": 1,
    "fare_amount": 20.0,
    "extra": 0.0,
    "mta_tax": 0.5,
    "tip_amount": 4.0,
    "tolls_amount": 0.0,
    "improvement_surcharge": 1.0,
    "total_amount": 28.0,          # 20 + 0 + 0.5 + 4 + 0 + 1 + 2.5 + 0
    "congestion_surcharge": 2.5,
    "Airport_fee": 0.0,
}

DTYPES = {
    "VendorID": "int32",
    "tpep_pickup_datetime": "datetime64[us]",
    "tpep_dropoff_datetime": "datetime64[us]",
    "PULocationID": "int32",
    "DOLocationID": "int32",
    "payment_type": "int64",
}


def trip(**changes) -> dict:
    """A valid trip with some fields changed, e.g. trip(fare_amount=-5)."""
    return {**VALID_TRIP, **changes}


def trips_df(rows: list[dict]) -> pd.DataFrame:
    """DataFrame with the same column types as the raw TLC Parquet files."""
    return pd.DataFrame(rows).astype(DTYPES)
