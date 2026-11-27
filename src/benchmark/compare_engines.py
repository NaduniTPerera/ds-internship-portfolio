"""Benchmark the 3 heaviest KPI queries: Postgres (loaded tables) vs DuckDB (raw Parquet).

Usage (from the repo root, with the Postgres container running and data loaded):
    uv run python -m benchmark.compare_engines            # 3 timed runs per query
    uv run python -m benchmark.compare_engines --runs 5

For each engine and query: 1 untimed warm-up run, then N timed runs; the
median is reported. The results of both engines are compared to make sure
they answer the question identically. Output: reports/day1_benchmark.md
"""

import argparse
import logging
import math
import os
import platform
import re
import statistics
import sys
import time
from collections.abc import Callable
from datetime import date
from decimal import Decimal

import duckdb
import psycopg

from ds_intern.config import PROJECT_ROOT, pg_params

logger = logging.getLogger(__name__)

POSTGRES_SQL = PROJECT_ROOT / "sql" / "002_kpis.sql"
DUCKDB_SQL = PROJECT_ROOT / "sql" / "003_duckdb_queries.sql"
REPORT = PROJECT_ROOT / "reports" / "day1_benchmark.md"
QUERIES = {
    4: "Busiest hour of week (heatmap)",
    8: "Share of airport trips",
    9: "Median trip duration by borough",
}
HEADER = re.compile(r"^-- Q(\d+)\.", re.MULTILINE)


def split_queries(sql: str) -> tuple[str, dict[int, str]]:
    """Split a SQL file on '-- Qn.' headers. Returns (setup SQL before Q1, {n: query})."""
    matches = list(HEADER.finditer(sql))
    setup = sql[: matches[0].start()] if matches else sql
    queries = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(sql)
        queries[int(m.group(1))] = sql[m.start():end].strip()
    return setup, queries


def normalise(rows: list[tuple]) -> list[tuple]:
    """Make rows from both engines comparable: numbers -> float, sorted."""
    def value(v):
        if isinstance(v, Decimal | float | int) and not isinstance(v, bool):
            return float(v)
        return v
    return sorted((tuple(value(v) for v in row) for row in rows), key=repr)


def same_results(a: list[tuple], b: list[tuple]) -> bool:
    if len(a) != len(b):
        return False
    for row_a, row_b in zip(a, b, strict=True):
        for x, y in zip(row_a, row_b, strict=True):
            if isinstance(x, float) and isinstance(y, float):
                # values are rounded to 1-2 decimals in SQL; allow last-digit rounding
                if not math.isclose(x, y, rel_tol=1e-9, abs_tol=0.051):
                    return False
            elif x != y:
                return False
    return True


def time_query(run: Callable[[], list[tuple]], runs: int) -> tuple[list[float], list[tuple]]:
    """1 warm-up + `runs` timed executions. Returns (seconds per run, result rows)."""
    rows = run()
    timings = []
    for _ in range(runs):
        started = time.perf_counter()
        rows = run()
        timings.append(time.perf_counter() - started)
    return timings, rows


def write_report(results: list[dict], runs: int, rows_pg: int) -> None:
    lines = [
        "# Day 1 - Postgres vs DuckDB runtimes",
        "",
        f"Run on {date.today():%Y-%m-%d}. Median of {runs} timed runs after 1 warm-up run.",
        "",
        "| Query | Question | Postgres 16 (s) | DuckDB on Parquet (s) | Speed-up | Same result |",
        "|---|---|---:|---:|---:|:---:|",
    ]
    for r in results:
        lines.append(
            f"| Q{r['q']} | {r['name']} | {r['pg']:.2f} | {r['duck']:.2f} "
            f"| {r['pg'] / r['duck']:.0f}x | {'yes' if r['match'] else 'NO'} |"
        )
    lines += [
        "",
        "Setup:",
        f"- Postgres 16 in Docker (WSL2), table `fact_trips` with {rows_pg:,} rows, "
        "default settings, no extra indexes.",
        f"- DuckDB {duckdb.__version__} in-process, reading the 6 raw Parquet files directly "
        "(no load step), same cleaning rule as the loader.",
        f"- Machine: {platform.system()} {platform.release()}, {os.cpu_count()} logical CPUs.",
        "",
        "Queries: Postgres versions in `sql/002_kpis.sql`, DuckDB versions in "
        "`sql/003_duckdb_queries.sql`.",
        "",
    ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Wrote %s", REPORT)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark Postgres vs DuckDB.")
    parser.add_argument("--runs", type=int, default=3, help="timed runs per query")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    os.chdir(PROJECT_ROOT)  # DuckDB SQL uses paths relative to the repo root
    _, pg_queries = split_queries(POSTGRES_SQL.read_text(encoding="utf-8"))
    duck_setup, duck_queries = split_queries(DUCKDB_SQL.read_text(encoding="utf-8"))

    duck = duckdb.connect()
    duck.execute(duck_setup)

    results = []
    with psycopg.connect(**pg_params()) as pg:
        rows_pg = pg.execute("SELECT COUNT(*) FROM fact_trips").fetchone()[0]
        for q, name in QUERIES.items():
            logger.info("Q%d %s: Postgres...", q, name)
            pg_times, pg_rows = time_query(lambda q=q: pg.execute(pg_queries[q]).fetchall(),
                                           args.runs)
            logger.info("Q%d %s: DuckDB...", q, name)
            duck_times, duck_rows = time_query(
                lambda q=q: duck.execute(duck_queries[q]).fetchall(), args.runs)

            match = same_results(normalise(pg_rows), normalise(duck_rows))
            result = {
                "q": q, "name": name, "match": match,
                "pg": statistics.median(pg_times), "duck": statistics.median(duck_times),
            }
            results.append(result)
            logger.info("Q%d: Postgres %.2f s, DuckDB %.2f s, same result: %s",
                        q, result["pg"], result["duck"], match)

    write_report(results, args.runs, rows_pg)
    return 0 if all(r["match"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
