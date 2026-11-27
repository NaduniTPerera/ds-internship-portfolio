"""Build the order-level analytical table (Day 3 Task 2).

Builds `order_analytics` in Postgres (sql/olist/002_order_analytics.sql), saves it
to data/processed/olist_orders.parquet for fast reuse in the statistics tasks,
and writes reports/day3/order_table.md with:
  - the row funnel (how many orders survive each step, and why rows are excluded)
  - a column profile made with the Day 2 profiler (quality.profile)

Usage:
    uv run python -m olist.order_table
Other code:
    from olist.order_table import load_orders
    df = load_orders()          # reads the Parquet file (builds it if missing)
"""

import argparse
import logging
import sys

import pandas as pd

from ds_intern import db
from ds_intern.config import PROCESSED_DATA_DIR, PROJECT_ROOT
from olist.load import DBNAME
from quality.profile import profile_dataframe, to_markdown

logger = logging.getLogger(__name__)

BUILD_SQL = PROJECT_ROOT / "sql" / "olist" / "002_order_analytics.sql"
PARQUET_PATH = PROCESSED_DATA_DIR / "olist_orders.parquet"
REPORT_PATH = PROJECT_ROOT / "reports" / "day3" / "order_table.md"

FUNNEL_SQL = """
SELECT step, count FROM (
    SELECT 1 AS n, 'all orders' AS step, COUNT(*) AS count FROM orders
    UNION ALL SELECT 2, 'status = delivered', COUNT(*) FROM orders
              WHERE order_status = 'delivered'
    UNION ALL SELECT 3, '... and has a delivery date', COUNT(*) FROM orders
              WHERE order_status = 'delivered' AND order_delivered_customer_date IS NOT NULL
    UNION ALL SELECT 4, 'in order_analytics (has items)', COUNT(*) FROM order_analytics
    UNION ALL SELECT 5, '... with a review score', COUNT(*) FROM order_analytics
              WHERE review_score IS NOT NULL
) f ORDER BY n
"""
FLOAT_COLUMNS = ["price", "freight"]   # NUMERIC in Postgres -> float for statistics


def query_df(conn, sql: str) -> pd.DataFrame:
    cur = conn.execute(sql)
    return pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])


def build() -> tuple[pd.DataFrame, pd.DataFrame]:
    """(Re)build the table in Postgres. Returns (orders DataFrame, funnel)."""
    with db.connect(DBNAME) as conn:
        db.run_sql_file(conn, BUILD_SQL)
        funnel = query_df(conn, FUNNEL_SQL)
        orders = query_df(conn, "SELECT * FROM order_analytics ORDER BY purchase_ts")
    orders[FLOAT_COLUMNS] = orders[FLOAT_COLUMNS].astype(float)
    for col in ["purchase_ts"]:
        orders[col] = pd.to_datetime(orders[col])
    for col in ["purchase_date", "estimated_delivery_date", "delivered_date"]:
        orders[col] = pd.to_datetime(orders[col])
    orders["review_score"] = orders["review_score"].astype("Int64")
    return orders, funnel


def validate(orders: pd.DataFrame) -> None:
    """Consistency checks; raise if the table breaks its own definitions."""
    problems = []
    if not orders["order_id"].is_unique:
        problems.append("order_id is not unique")
    if not (orders["is_late"] == (orders["days_late"] > 0)).all():
        problems.append("is_late does not match days_late > 0")
    if orders["customer_region"].isna().any():
        problems.append("some customer_state has no region")
    scores = orders["review_score"].dropna()
    if not scores.between(1, 5).all():
        problems.append("review_score outside 1-5")
    if (orders["delivery_days"] < 0).any():
        problems.append("delivered before purchase")
    if problems:
        raise ValueError("order_analytics failed checks: " + "; ".join(problems))


def load_orders() -> pd.DataFrame:
    """The analytical table as a DataFrame (from the Parquet cache, built if missing)."""
    if not PARQUET_PATH.exists():
        orders, _ = build()
        save(orders)
    return pd.read_parquet(PARQUET_PATH)


def save(orders: pd.DataFrame) -> None:
    PARQUET_PATH.parent.mkdir(parents=True, exist_ok=True)
    orders.to_parquet(PARQUET_PATH, index=False)
    logger.info("Saved %s", PARQUET_PATH)


def write_report(orders: pd.DataFrame, funnel: pd.DataFrame) -> None:
    late = orders["is_late"]
    scored = orders["review_score"].notna()
    lines = [
        "# Day 3 - Order-level analytical table",
        "",
        "Table `order_analytics` in the `olist` database "
        "([`sql/olist/002_order_analytics.sql`](../../sql/olist/002_order_analytics.sql)), "
        "also saved as `data/processed/olist_orders.parquet`. One row = one delivered order.",
        "",
        "## Row funnel",
        "",
        "| Step | Orders |",
        "|---|---:|",
        *[f"| {r.step} | {r.count:,} |" for r in funnel.itertuples(index=False)],
        "",
        "## Headline numbers",
        "",
        f"- Late orders: {late.sum():,} of {len(orders):,} ({100 * late.mean():.1f}%)",
        f"- Median days late among late orders: "
        f"{orders.loc[late, 'days_late'].median():.0f}; "
        f"median days early among on-time orders: "
        f"{-orders.loc[~late, 'days_late'].median():.0f}",
        f"- Mean review score: on time {orders.loc[~late & scored, 'review_score'].mean():.2f}, "
        f"late {orders.loc[late & scored, 'review_score'].mean():.2f}",
        f"- Orders with more than one seller: {(orders['n_sellers'] > 1).sum():,} "
        f"({100 * (orders['n_sellers'] > 1).mean():.1f}%). Seller and category come "
        "from the most expensive item.",
        f"- Distinct customers (`customer_unique_id`): "
        f"{orders['customer_unique_id'].nunique():,} for {len(orders):,} orders",
        "",
        to_markdown(profile_dataframe(orders.drop(columns=["order_id", "customer_unique_id"])),
                    "Column profile (Day 2 profiler)"),
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Wrote %s", REPORT_PATH)


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description="Build the Olist order-level table.").parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    orders, funnel = build()
    validate(orders)
    save(orders)
    write_report(orders, funnel)
    logger.info("order_analytics: %d rows, %d columns", *orders.shape)
    return 0


if __name__ == "__main__":
    sys.exit(main())
