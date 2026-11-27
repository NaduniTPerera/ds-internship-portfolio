"""Cleaning policy for every validation rule, and the cleaned monthly Parquet files.

Each rule in quality.schema.RULES gets exactly one policy (in POLICY):
    drop           delete the row: impossible and cannot be repaired
    cap            limit a value to its allowed range, keep the row
    impute         replace the bad value (here: with NULL = unknown), keep the row
    keep-and-flag  keep the row unchanged, add a boolean flag column

After cleaning, all rules are run again on the cleaned data; if any "error" rule
still fails, the script stops (the policy must fully fix every error).

Output: data/processed/yellow_tripdata_clean_<YYYY-MM>.parquet (git-ignored)
        reports/day2/cleaning_policy.md

Usage:
    uv run python -m quality.clean                     # all six months
    uv run python -m quality.clean --months 2024-01
"""

import argparse
import gc
import logging
import sys
from dataclasses import dataclass
from datetime import date

import pandas as pd

from ds_intern.config import PROCESSED_DATA_DIR, PROJECT_ROOT
from quality.io import MONTHS, load_month, parse_month
from quality.schema import RULES, RULES_BY_NAME, rule_results

logger = logging.getLogger(__name__)

REPORT_PATH = PROJECT_ROOT / "reports" / "day2" / "cleaning_policy.md"


@dataclass(frozen=True)
class Policy:
    action: str          # drop / cap / impute / keep-and-flag
    reason: str


POLICY: dict[str, Policy] = {
    "vendor_id_valid": Policy(
        "drop", "Unknown data source; cannot be trusted or joined to dim_vendor."),
    "payment_type_valid": Policy(
        "drop", "Cannot be joined to dim_payment_type; payment meaning unknown."),
    "zone_ids_valid": Policy(
        "drop", "Cannot be joined to dim_zone; location unknown."),
    "store_and_fwd_flag_valid": Policy(
        "impute", "Unimportant technical field; set to NULL instead of losing the trip."),
    "pickup_in_file_month": Policy(
        "drop", "Clock or file error (some years 2002-2026); breaks monthly totals."),
    "dropoff_after_pickup": Policy(
        "drop", "Physically impossible; duration and speed cannot be computed."),
    "duration_under_6h": Policy(
        "drop", "Meter left running; recorded time and fare do not describe a real trip."),
    "passenger_count_1_to_6": Policy(
        "impute", "Driver-entered field (0 = not entered). The trip is valid, so set the "
                  "count to NULL (unknown) and flag it. No fake value is invented."),
    "trip_distance_positive": Policy(
        "drop", "No distance recorded (cancelled or meter not used); unusable for "
                "fare-per-mile, speed and distance analysis."),
    "speed_plausible": Policy(
        "drop", "Distance or time is wrong, and we cannot tell which one to fix."),
    "fare_amount_non_negative": Policy(
        "drop", "Refunds, voids and disputes: real accounting events, but not trips."),
    "tip_amount_non_negative": Policy(
        "cap", "Small negative adjustment on an otherwise valid trip; cap at 0."),
    "total_amount_non_negative": Policy(
        "drop", "Refund or void rows (see fare_amount); not trips."),
    "rate_code_known": Policy(
        "keep-and-flag", "99 = 'unknown' is a valid dictionary value; flag for analyses "
                         "that need the rate code."),
    "total_matches_components": Policy(
        "keep-and-flag", "Vendor recording convention (vendor 1 counts the congestion "
                         "surcharge twice, Flex Fare leaves it NULL). The money is correct."),
    "flex_fare_fields_present": Policy(
        "keep-and-flag", "Missing by design for Flex Fare trips (payment_type 0); "
                         "imputing surcharges would invent data."),
}

# Flag columns added to the cleaned data (True = the rule failed or a value was changed).
FLAG_COLUMNS = {
    "rate_code_known": "flag_rate_code_unknown",
    "total_matches_components": "flag_total_mismatch",
    "flex_fare_fields_present": "flag_flex_fare_nulls",
    "passenger_count_1_to_6": "flag_passenger_count_imputed",
    "tip_amount_non_negative": "flag_tip_capped",
    "store_and_fwd_flag_valid": "flag_store_and_fwd_imputed",
}


def check_policy_covers_all_rules() -> None:
    missing = {r.name for r in RULES} - set(POLICY)
    if missing:
        raise ValueError(f"No cleaning policy for rules: {sorted(missing)}")


def clean_month(df: pd.DataFrame, month: date) -> tuple[pd.DataFrame, dict[str, int]]:
    """Apply the policy. Returns (cleaned DataFrame, {rule: rows affected})."""
    check_policy_covers_all_rules()
    results = {name: passed.astype(bool) for name, passed in rule_results(df, month).items()}
    affected = {name: int((~passed).sum()) for name, passed in results.items()}

    drop = pd.Series(False, index=df.index)
    for name, passed in results.items():
        if POLICY[name].action == "drop":
            drop |= ~passed
    affected["_dropped_total"] = int(drop.sum())

    keep = ~drop
    clean = df.loc[keep].copy()
    failing = {name: ~passed[keep] for name, passed in results.items()}

    # impute: invalid values become NULL (unknown)
    clean.loc[failing["passenger_count_1_to_6"], "passenger_count"] = float("nan")
    clean.loc[failing["store_and_fwd_flag_valid"], "store_and_fwd_flag"] = None
    # cap: negative tips become 0
    clean.loc[failing["tip_amount_non_negative"], "tip_amount"] = 0.0
    # flags for every kept-but-changed or kept-and-flagged row
    for rule_name, column in FLAG_COLUMNS.items():
        clean[column] = failing[rule_name].to_numpy()

    clean["source_month"] = pd.Timestamp(month)
    return clean.reset_index(drop=True), affected


def verify_clean(clean: pd.DataFrame, month: date) -> None:
    """Re-run every rule; no 'error' rule may fail on cleaned data."""
    still_failing = {
        name: int((~passed.astype(bool)).sum())
        for name, passed in rule_results(clean, month).items()
        if RULES_BY_NAME[name].severity == "error" and not passed.all()
    }
    if still_failing:
        raise AssertionError(f"Cleaned data still fails error rules: {still_failing}")


def write_policy_report(totals: dict[str, int], rows_in: int, rows_out: int) -> None:
    lines = [
        "# Day 2 - Cleaning policy",
        "",
        f"Input: {rows_in:,} raw rows (Jan-Jun 2024). Output: {rows_out:,} rows "
        f"({100 * rows_out / rows_in:.2f}% kept, {rows_in - rows_out:,} dropped).",
        "Cleaned files: `data/processed/yellow_tripdata_clean_<YYYY-MM>.parquet` "
        "(not in git). Code: `src/quality/clean.py`.",
        "",
        "After cleaning, all 16 rules are re-run on the cleaned data, and every **error** "
        "rule passes with 0 failures.",
        "",
        "| Rule | Severity | Policy | Rows affected | Reason |",
        "|---|---|---|---:|---|",
    ]
    for rule in RULES:
        p = POLICY[rule.name]
        flag = FLAG_COLUMNS.get(rule.name)
        reason = p.reason + (f" Flag column: `{flag}`." if flag else "")
        lines.append(f"| `{rule.name}` | {rule.severity} | **{p.action}** "
                     f"| {totals[rule.name]:,} | {reason} |")
    lines += [
        "",
        "Rows affected = raw rows failing the rule. One row can fail several rules, so the "
        f"drop counts add up to more than the {rows_in - rows_out:,} rows actually dropped.",
        "",
        "## Principles",
        "",
        "- **Drop only what is impossible and cannot be repaired.** Every dropped row is "
        "lost information.",
        "- **Never invent values.** Invalid passenger counts become NULL (unknown), not a "
        "guessed number.",
        "- **Explained differences are flagged, not deleted.** Users of the data can filter "
        "on the `flag_*` columns if their analysis needs it.",
        "- **The policy is code**, so it is applied the same way every time and can be "
        "reviewed.",
        "",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Wrote %s", REPORT_PATH)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clean raw taxi months with the policy.")
    parser.add_argument("--months", nargs="+", metavar="YYYY-MM")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s - %(message)s")

    months = [parse_month(m) for m in args.months] if args.months else MONTHS
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    totals: dict[str, int] = {}
    rows_in = rows_out = 0

    for month in months:
        df = load_month(month)
        clean, affected = clean_month(df, month)
        verify_clean(clean, month)

        out = PROCESSED_DATA_DIR / f"yellow_tripdata_clean_{month:%Y-%m}.parquet"
        clean.to_parquet(out, index=False)
        logger.info("%s: %d -> %d rows (dropped %d), saved %s",
                    f"{month:%Y-%m}", len(df), len(clean), affected["_dropped_total"], out.name)

        rows_in += len(df)
        rows_out += len(clean)
        for name, n in affected.items():
            totals[name] = totals.get(name, 0) + n
        del df, clean
        gc.collect()

    write_policy_report(totals, rows_in, rows_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
