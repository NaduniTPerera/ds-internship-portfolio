"""Data quality gate for one month of raw taxi data (for CI / Airflow).

Usage:
    uv run python -m quality.run_checks --month 2024-01 --max-failure-pct 5
    uv run python -m quality.run_checks --month 2024-01 --max-failure-pct 5 --json out.json

Failure rate = rows that break at least one "error" rule / all rows, in percent.
"warn" rules are logged but do not count.

Exit codes (what CI / Airflow look at):
    0  checks passed   (failure rate <= threshold)
    1  checks FAILED   (failure rate >  threshold) -> the data is bad
    2  could not run   (missing file, bad arguments) -> the pipeline is broken
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from ds_intern.config import RAW_DATA_DIR
from quality.io import load_month, parse_month
from quality.schema import error_failure_mask, evaluate_rules, rule_results

logger = logging.getLogger(__name__)

EXIT_PASSED, EXIT_FAILED, EXIT_ERROR = 0, 1, 2


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate one month of raw taxi data and fail if too many rows are bad.")
    parser.add_argument("--month", required=True, metavar="YYYY-MM", help="month to check")
    parser.add_argument("--max-failure-pct", required=True, type=float, metavar="PCT",
                        help="maximum allowed %% of rows failing an error rule, e.g. 5")
    parser.add_argument("--json", type=Path, metavar="PATH",
                        help="also write the results as JSON (for other pipeline steps)")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DATA_DIR, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not 0 <= args.max_failure_pct <= 100:
        parser.error("--max-failure-pct must be between 0 and 100")
    return args


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    try:
        args = parse_args(argv)
    except SystemExit as exc:          # argparse exits with 2 on bad arguments
        return EXIT_ERROR if exc.code else EXIT_PASSED

    try:
        month = parse_month(args.month)
        df = load_month(month, raw_dir=args.raw_dir)
    except (ValueError, FileNotFoundError) as exc:
        logger.error("Cannot run checks: %s", exc)
        return EXIT_ERROR

    rows = len(df)
    if rows == 0:
        logger.error("%s has no rows", args.month)
        return EXIT_ERROR

    table = evaluate_rules(df, month)
    failing_rows = int(error_failure_mask(rule_results(df, month)).sum())
    failure_pct = 100 * failing_rows / rows

    for r in table.itertuples(index=False):
        if r.rows_failing == 0:
            continue
        log = logger.warning if r.severity == "warn" else logger.info
        log("[%s] %-26s %9d rows (%6.3f%%)  e.g. %s",
            r.severity, r.rule, r.rows_failing, r.pct_failing, r.example_bad_row)

    passed = failure_pct <= args.max_failure_pct
    verdict = "PASSED" if passed else "FAILED"
    log = logger.info if passed else logger.error
    log("%s %s: %d of %d rows (%.2f%%) fail an error rule; threshold %.2f%%",
        args.month, verdict, failing_rows, rows, failure_pct, args.max_failure_pct)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({
            "month": args.month,
            "rows": rows,
            "rows_failing": failing_rows,
            "failure_pct": round(failure_pct, 4),
            "threshold_pct": args.max_failure_pct,
            "passed": passed,
            "rules": table.to_dict(orient="records"),
        }, indent=2), encoding="utf-8")
        logger.info("Wrote %s", args.json)

    return EXIT_PASSED if passed else EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
