"""Tests for the validation rules (src/quality/schema.py) on tiny hand-made DataFrames.

Each rule gets one good row (VALID_TRIP, passes every rule) and one bad row
built to break THAT rule only, which also proves no rule fires by accident.
"""

from datetime import date

import pandas as pd
import pandera.pandas as pa
import pytest

from quality.schema import RULES, build_schema, error_failure_mask, evaluate_rules, rule_results
from tests.helpers import trip, trips_df

JAN = date(2024, 1, 1)
PICKUP = pd.Timestamp("2024-01-15 08:00:00")

# rule -> changes to a valid trip that break exactly that rule
BAD_ROWS = {
    "vendor_id_valid": {"VendorID": 3},
    "payment_type_valid": {"payment_type": 9},
    "zone_ids_valid": {"PULocationID": 300},
    "store_and_fwd_flag_valid": {"store_and_fwd_flag": "X"},
    "pickup_in_file_month": {"tpep_pickup_datetime": pd.Timestamp("2023-12-31 23:50:00"),
                             "tpep_dropoff_datetime": pd.Timestamp("2024-01-01 00:10:00")},
    "dropoff_after_pickup": {"tpep_dropoff_datetime": PICKUP},
    "duration_under_6h": {"tpep_dropoff_datetime": PICKUP + pd.Timedelta(hours=7)},
    "passenger_count_1_to_6": {"passenger_count": 0.0},
    "trip_distance_positive": {"trip_distance": 0.0},
    "speed_plausible": {"tpep_dropoff_datetime": PICKUP + pd.Timedelta(minutes=1)},  # 180 mph
    # money fields are linked: keep the total consistent so only the target rule fails
    "fare_amount_non_negative": {"fare_amount": -20.0, "tip_amount": 44.0},
    "tip_amount_non_negative": {"fare_amount": 25.0, "tip_amount": -1.0},
    "total_amount_non_negative": {"extra": -40.0, "total_amount": -12.0},
    "rate_code_known": {"RatecodeID": 99.0},
    "total_matches_components": {"total_amount": 30.5},
    "flex_fare_fields_present": {"Airport_fee": float("nan")},
}


def failing_rules(row: dict) -> set[str]:
    results = rule_results(trips_df([row]), JAN)
    return {name for name, passed in results.items() if not bool(passed.iloc[0])}


def test_bad_rows_cover_every_rule():
    assert set(BAD_ROWS) == {r.name for r in RULES}


@pytest.mark.parametrize("rule_name", list(BAD_ROWS))
def test_each_rule_good_row_passes_bad_row_fails(rule_name):
    """Test 1: the good row passes all rules; the bad row fails ONLY its own rule."""
    assert failing_rules(trip()) == set()
    assert failing_rules(trip(**BAD_ROWS[rule_name])) == {rule_name}


def test_evaluate_rules_counts_percent_and_example():
    """Test 2: the report table counts failures and shows an example bad row."""
    df = trips_df([
        trip(),
        trip(**BAD_ROWS["fare_amount_non_negative"]),
        trip(**BAD_ROWS["passenger_count_1_to_6"]),
    ])
    table = evaluate_rules(df, JAN).set_index("rule")

    assert table.loc["fare_amount_non_negative", "rows_failing"] == 1
    assert table.loc["fare_amount_non_negative", "pct_failing"] == pytest.approx(33.333)
    assert table.loc["fare_amount_non_negative", "example_bad_row"] == "fare_amount=-20"
    assert table.loc["passenger_count_1_to_6", "example_bad_row"] == "passenger_count=0"
    assert table.loc["vendor_id_valid", "rows_failing"] == 0
    assert table.loc["vendor_id_valid", "example_bad_row"] == ""


def test_severity_warn_reports_error_fails():
    """Test 3: warn rules only warn; error rules fail the pandera validation."""
    schema = build_schema(JAN)

    warn_only = trips_df([trip(), trip(RatecodeID=99.0)])
    assert not error_failure_mask(rule_results(warn_only, JAN)).any()
    with pytest.warns(pa.errors.SchemaWarning):
        schema.validate(warn_only, lazy=True)          # passes, but warns

    with_error = trips_df([trip(), trip(passenger_count=0.0)])
    assert error_failure_mask(rule_results(with_error, JAN)).tolist() == [False, True]
    with pytest.raises(pa.errors.SchemaErrors):
        schema.validate(with_error, lazy=True)
