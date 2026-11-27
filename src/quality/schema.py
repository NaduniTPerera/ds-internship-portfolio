"""Validation rules for raw NYC Yellow Taxi data, as a pandera DataFrameSchema.

Each rule is defined ONCE (in RULES) and used two ways:
1. build_schema(month) -> pandera DataFrameSchema with one named Check per rule
   (severity "warn" rules use raise_warning=True, so they never fail validation).
2. evaluate_rules(df, month) -> table: rule, rows failing, % failing, example bad row.
   It runs each pandera Check and reads its boolean pass/fail output.

Rules come from the TLC Yellow Taxi data dictionary plus checks for physically
impossible values. A rule function returns a boolean Series: True = row passes.
Missing values are handled explicitly in each rule (range rules ignore NULLs;
the 'flex_fare_fields_present' rule reports them).

CLI (all months -> reports/day2/validation_report.md):
    uv run python -m quality.schema
"""

import argparse
import gc
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd
import pandera.pandas as pa

from ds_intern.config import PROJECT_ROOT
from quality.io import MONTHS, load_month, parse_month

logger = logging.getLogger(__name__)

REPORT_PATH = PROJECT_ROOT / "reports" / "day2" / "validation_report.md"

PICKUP, DROPOFF = "tpep_pickup_datetime", "tpep_dropoff_datetime"
VALID_VENDORS = {1, 2, 6, 7}          # data dictionary
VALID_RATE_CODES = {1, 2, 3, 4, 5, 6}  # 99 = "Null/unknown" in the dictionary
VALID_PAYMENT_TYPES = {0, 1, 2, 3, 4, 5, 6}
MIN_ZONE, MAX_ZONE = 1, 265
MAX_DURATION = pd.Timedelta(hours=6)
MAX_SPEED_MPH = 80
TOTAL_TOLERANCE = 0.01                 # dollars
COMPONENTS = ["fare_amount", "extra", "mta_tax", "tip_amount", "tolls_amount",
              "improvement_surcharge", "congestion_surcharge", "Airport_fee"]
FLEX_FARE_NULL_COLUMNS = ["passenger_count", "RatecodeID", "store_and_fwd_flag",
                          "congestion_surcharge", "Airport_fee"]


@dataclass(frozen=True)
class Rule:
    name: str
    description: str
    columns: list[str]                  # shown in the example bad row
    severity: str                       # "error" or "warn"
    check: Callable[[pd.DataFrame, date], pd.Series]


def _month_bounds(month: date) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(datetime(month.year, month.month, 1))
    return start, start + pd.offsets.MonthBegin(1)


def _in_month(df: pd.DataFrame, month: date) -> pd.Series:
    start, end = _month_bounds(month)
    return (df[PICKUP] >= start) & (df[PICKUP] < end)


def _duration(df: pd.DataFrame) -> pd.Series:
    return df[DROPOFF] - df[PICKUP]


def _speed_ok(df: pd.DataFrame, month: date) -> pd.Series:
    hours = _duration(df).dt.total_seconds() / 3600
    measurable = (df["trip_distance"] > 0) & (hours > 0)
    speed = df["trip_distance"].where(measurable) / hours.where(measurable)
    return ~measurable | (speed <= MAX_SPEED_MPH)


def _total_matches(df: pd.DataFrame, month: date) -> pd.Series:
    parts = df[COMPONENTS].fillna(0).sum(axis=1)
    return (df["total_amount"] - parts).abs() <= TOTAL_TOLERANCE


RULES: list[Rule] = [
    Rule("vendor_id_valid", "VendorID is a code from the data dictionary (1, 2, 6, 7)",
         ["VendorID"], "error",
         lambda df, m: df["VendorID"].isin(VALID_VENDORS)),
    Rule("payment_type_valid", "payment_type is a dictionary code (0-6)",
         ["payment_type"], "error",
         lambda df, m: df["payment_type"].isin(VALID_PAYMENT_TYPES)),
    Rule("zone_ids_valid", f"PU/DO LocationID are valid zones ({MIN_ZONE}-{MAX_ZONE})",
         ["PULocationID", "DOLocationID"], "error",
         lambda df, m: df["PULocationID"].between(MIN_ZONE, MAX_ZONE)
         & df["DOLocationID"].between(MIN_ZONE, MAX_ZONE)),
    Rule("store_and_fwd_flag_valid", "store_and_fwd_flag is Y or N (NULL allowed)",
         ["store_and_fwd_flag"], "error",
         lambda df, m: df["store_and_fwd_flag"].isna()
         | df["store_and_fwd_flag"].isin(["Y", "N"])),
    Rule("pickup_in_file_month", "pickup time falls inside the file's month",
         [PICKUP], "error",
         lambda df, m: _in_month(df, m)),
    Rule("dropoff_after_pickup", "dropoff is strictly after pickup",
         [PICKUP, DROPOFF], "error",
         lambda df, m: df[DROPOFF] > df[PICKUP]),
    Rule("duration_under_6h", "trip duration is less than 6 hours",
         [PICKUP, DROPOFF], "error",
         lambda df, m: _duration(df) < MAX_DURATION),
    Rule("passenger_count_1_to_6", "passenger_count between 1 and 6 (NULL allowed)",
         ["passenger_count"], "error",
         lambda df, m: df["passenger_count"].isna() | df["passenger_count"].between(1, 6)),
    Rule("trip_distance_positive", "trip_distance is greater than 0 miles",
         ["trip_distance"], "error",
         lambda df, m: df["trip_distance"] > 0),
    Rule("speed_plausible", f"average speed is at most {MAX_SPEED_MPH} mph",
         ["trip_distance", PICKUP, DROPOFF], "error",
         _speed_ok),
    Rule("fare_amount_non_negative", "fare_amount >= 0",
         ["fare_amount"], "error",
         lambda df, m: df["fare_amount"] >= 0),
    Rule("tip_amount_non_negative", "tip_amount >= 0",
         ["tip_amount"], "error",
         lambda df, m: df["tip_amount"] >= 0),
    Rule("total_amount_non_negative", "total_amount >= 0",
         ["total_amount"], "error",
         lambda df, m: df["total_amount"] >= 0),
    Rule("rate_code_known", "RatecodeID is 1-6 (99 = unknown; NULL allowed)",
         ["RatecodeID"], "warn",
         lambda df, m: df["RatecodeID"].isna() | df["RatecodeID"].isin(VALID_RATE_CODES)),
    Rule("total_matches_components",
         f"total_amount = sum of fare, extra, taxes, tip, tolls, surcharges, fees "
         f"(within ${TOTAL_TOLERANCE})",
         ["VendorID", "total_amount", "fare_amount", "extra", "congestion_surcharge"], "warn",
         _total_matches),
    Rule("flex_fare_fields_present",
         "passenger_count, RatecodeID, store_and_fwd_flag, congestion_surcharge, "
         "Airport_fee are not NULL",
         ["payment_type", *FLEX_FARE_NULL_COLUMNS], "warn",
         lambda df, m: df[FLEX_FARE_NULL_COLUMNS].notna().all(axis=1)),
]
RULES_BY_NAME = {rule.name: rule for rule in RULES}


def build_schema(month: date) -> pa.DataFrameSchema:
    """pandera schema: expected columns/dtypes plus one named Check per rule."""
    def column(dtype, nullable=False):
        return pa.Column(dtype, nullable=nullable)

    columns = {
        "VendorID": column("int32"),
        PICKUP: column("datetime64[us]"),
        DROPOFF: column("datetime64[us]"),
        "passenger_count": column("float64", nullable=True),
        "trip_distance": column("float64"),
        "RatecodeID": column("float64", nullable=True),
        "store_and_fwd_flag": column(None, nullable=True),   # text; dtype varies by pandas version
        "PULocationID": column("int32"),
        "DOLocationID": column("int32"),
        "payment_type": column("int64"),
        "fare_amount": column("float64"),
        "extra": column("float64"),
        "mta_tax": column("float64"),
        "tip_amount": column("float64"),
        "tolls_amount": column("float64"),
        "improvement_surcharge": column("float64"),
        "total_amount": column("float64"),
        "congestion_surcharge": column("float64", nullable=True),
        "Airport_fee": column("float64", nullable=True),
    }
    checks = [
        pa.Check(
            (lambda df, rule=rule: rule.check(df, month)),
            name=rule.name,
            error=rule.description,
            raise_warning=(rule.severity == "warn"),
            ignore_na=False,   # each rule decides itself how NULLs are treated
        )
        for rule in RULES
    ]
    return pa.DataFrameSchema(columns=columns, checks=checks, name=f"yellow_taxi_{month:%Y_%m}")


def rule_results(df: pd.DataFrame, month: date) -> dict[str, pd.Series]:
    """Run every pandera Check. Returns {rule name: boolean Series, True = passes}."""
    schema = build_schema(month)
    return {check.name: check(df).check_output for check in schema.checks}


def _example(df: pd.DataFrame, failing: pd.Series, rule: Rule) -> str:
    if not failing.any():
        return ""
    row = df.loc[failing.idxmax(), rule.columns]
    parts = []
    for col, value in row.items():
        if isinstance(value, pd.Timestamp):
            value = value.strftime("%Y-%m-%d %H:%M:%S")
        elif isinstance(value, float):
            value = "NULL" if pd.isna(value) else f"{value:g}"
        parts.append(f"{col}={value}")
    return ", ".join(parts)


def evaluate_rules(df: pd.DataFrame, month: date) -> pd.DataFrame:
    """Table with one row per rule: rows failing, % failing, example bad row."""
    rows = len(df)
    records = []
    for name, passed in rule_results(df, month).items():
        rule = RULES_BY_NAME[name]
        failing = ~passed.astype(bool)
        n_fail = int(failing.sum())
        records.append({
            "rule": name,
            "severity": rule.severity,
            "description": rule.description,
            "rows_failing": n_fail,
            "pct_failing": round(100 * n_fail / rows, 3) if rows else 0.0,
            "example_bad_row": _example(df, failing, rule),
        })
    return pd.DataFrame(records)


def error_failure_mask(results: dict[str, pd.Series]) -> pd.Series:
    """True for rows that break at least one 'error' rule."""
    failing = [~passed.astype(bool) for name, passed in results.items()
               if RULES_BY_NAME[name].severity == "error"]
    return pd.concat(failing, axis=1).any(axis=1)


def write_report(totals: pd.DataFrame, per_month: list[dict]) -> None:
    total_rows = sum(m["rows"] for m in per_month)
    lines = [
        "# Day 2 - Validation report (raw data, Jan-Jun 2024)",
        "",
        f"Rows checked: {total_rows:,}. Rules: {len(RULES)} "
        f"({sum(r.severity == 'error' for r in RULES)} error, "
        f"{sum(r.severity == 'warn' for r in RULES)} warn). "
        "Rule definitions: `src/quality/schema.py`.",
        "",
        "- **error**: the row is wrong or impossible. Counts toward the CI failure rate.",
        "- **warn**: suspicious or explained by how the data is recorded. Reported only.",
        "",
        "| Rule | Severity | Description | Rows failing | % failing | Example bad row |",
        "|---|---|---|---:|---:|---|",
    ]
    for r in totals.itertuples(index=False):
        lines.append(f"| `{r.rule}` | {r.severity} | {r.description} | {r.rows_failing:,} "
                     f"| {r.pct_failing:.3f} | {r.example_bad_row} |")
    lines += [
        "",
        "## Rows failing at least one error rule, per month",
        "",
        "| Month | Rows | Rows failing | % failing |",
        "|---|---:|---:|---:|",
    ]
    for m in per_month:
        lines.append(f"| {m['month']} | {m['rows']:,} | {m['failing']:,} "
                     f"| {100 * m['failing'] / m['rows']:.2f} |")
    lines += [
        "",
        "## Root causes found while investigating",
        "",
        "- **`total_matches_components` (29%) is a recording difference, not wrong money.**",
        "  Vendor 1 includes the $2.50 congestion surcharge inside `extra` *and* in",
        "  `congestion_surcharge`, so adding all components counts it twice (difference",
        "  -$2.50, about 3.8M trips). Flex Fare trips (payment_type 0, mostly vendor 2) include",
        "  $2.50 in the total but leave `congestion_surcharge` NULL (difference +$2.50). Almost",
        "  every mismatch is exactly +/-$2.50, +/-$1.75 (airport fee) or a combination.",
        "- **`flex_fare_fields_present`**: Flex Fare trips (payment_type 0) never record",
        "  passenger count, rate code, store-and-forward flag or the surcharges. This is",
        "  by design, so it is a warning, not an error.",
        "- **Negative `fare_amount` / `total_amount`**: refunds, voids and disputes are",
        "  recorded as negative rows. They are real events, but they are not trips.",
        "- **`trip_distance` = 0 and `passenger_count` = 0**: driver-entered or meter",
        "  values that were never filled in (cancelled trips, meter not reset).",
        "- **`pickup_in_file_month`**: 149 rows, the same 149 the Day 1 loader dropped.",
        "",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Wrote %s", REPORT_PATH)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate validation rules on raw months.")
    parser.add_argument("--months", nargs="+", metavar="YYYY-MM")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s - %(message)s")

    months = [parse_month(m) for m in args.months] if args.months else MONTHS
    totals: pd.DataFrame | None = None
    per_month = []
    for month in months:
        df = load_month(month)
        results = rule_results(df, month)
        table = evaluate_rules(df, month)
        failing = int(error_failure_mask(results).sum())
        per_month.append({"month": f"{month:%Y-%m}", "rows": len(df), "failing": failing})
        logger.info("%s: %d rows, %d fail an error rule", f"{month:%Y-%m}", len(df), failing)

        if totals is None:
            totals = table
        else:
            totals["rows_failing"] += table["rows_failing"]
            # keep the first example found; fill it from later months if still empty
            empty = totals["example_bad_row"] == ""
            totals.loc[empty, "example_bad_row"] = table.loc[empty, "example_bad_row"]
        del df, results
        gc.collect()

    total_rows = sum(m["rows"] for m in per_month)
    totals["pct_failing"] = (100 * totals["rows_failing"] / total_rows).round(3)
    write_report(totals, per_month)
    return 0


if __name__ == "__main__":
    sys.exit(main())
