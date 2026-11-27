"""Column profiling: one row per column with dtype, nulls, distinct values, min/max, top values.

Reusable on any pandas DataFrame:
    from quality.profile import profile_dataframe
    report = profile_dataframe(df)

CLI (writes reports/day2/profile_<month>.csv and a Markdown version):
    uv run python -m quality.profile                    # all six months
    uv run python -m quality.profile --months 2024-01
"""

import argparse
import gc
import logging
import sys
from datetime import date

import pandas as pd

from ds_intern.config import PROJECT_ROOT
from quality.io import MONTHS, load_month, parse_month

logger = logging.getLogger(__name__)

REPORT_DIR = PROJECT_ROOT / "reports" / "day2"
TOP_N = 3


def format_value(value) -> str:
    """Short, readable text for one value (used in min/max/top columns)."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return "NULL"
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def profile_column(series: pd.Series, top_n: int = TOP_N) -> dict:
    """Profile one column."""
    rows = len(series)
    nulls = int(series.isna().sum())
    non_null = series.dropna()

    if len(non_null):
        minimum, maximum = non_null.min(), non_null.max()
    else:
        minimum = maximum = None

    counts = series.value_counts(dropna=False).head(top_n)
    top_values = ", ".join(
        f"{format_value(v)} ({c / rows:.1%})" for v, c in counts.items()
    ) if rows else ""

    return {
        "column": series.name,
        "dtype": str(series.dtype),
        "rows": rows,
        "nulls": nulls,
        "null_pct": round(100 * nulls / rows, 2) if rows else 0.0,
        "distinct": int(series.nunique(dropna=True)),
        "min": format_value(minimum),
        "max": format_value(maximum),
        "top_values": top_values,
    }


def profile_dataframe(df: pd.DataFrame, top_n: int = TOP_N) -> pd.DataFrame:
    """Profile every column of a DataFrame. Returns one row per column."""
    return pd.DataFrame([profile_column(df[col], top_n) for col in df.columns])


def to_markdown(report: pd.DataFrame, title: str) -> str:
    """Render a profile as a Markdown table (no extra dependency needed)."""
    headers = list(report.columns)
    lines = [f"## {title}", "", "| " + " | ".join(headers) + " |",
             "|" + "|".join("---" for _ in headers) + "|"]
    for row in report.itertuples(index=False):
        cells = [f"{v:,}" if isinstance(v, int) else str(v) for v in row]
        lines.append("| " + " | ".join(c.replace("|", "/") for c in cells) + " |")
    return "\n".join(lines) + "\n"


def profile_month(month: date) -> pd.DataFrame:
    df = load_month(month)
    logger.info("%s: profiling %d rows x %d columns", f"{month:%Y-%m}", len(df), df.shape[1])
    report = profile_dataframe(df)
    del df
    gc.collect()  # free the month before loading the next one (laptop has limited RAM)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Profile raw taxi months.")
    parser.add_argument("--months", nargs="+", metavar="YYYY-MM",
                        help="months to profile (default: 2024-01 to 2024-06)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s - %(message)s")

    months = [parse_month(m) for m in args.months] if args.months else MONTHS
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    sections = ["# Day 2 - Column profiles (raw data)", ""]
    for month in months:
        report = profile_month(month)
        csv_path = REPORT_DIR / f"profile_{month:%Y-%m}.csv"
        report.to_csv(csv_path, index=False)
        sections.append(to_markdown(report, f"{month:%Y-%m}"))
        logger.info("Wrote %s", csv_path)

    md_path = REPORT_DIR / "profile.md"
    md_path.write_text("\n".join(sections), encoding="utf-8")
    logger.info("Wrote %s", md_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
