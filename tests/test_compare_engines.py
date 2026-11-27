from decimal import Decimal

from benchmark.compare_engines import (
    DUCKDB_SQL,
    POSTGRES_SQL,
    QUERIES,
    normalise,
    same_results,
    split_queries,
)


def test_split_queries_finds_headers():
    sql = "CREATE VIEW v AS SELECT 1;\n-- Q1. a\nSELECT 1;\n-- Q2. b\nSELECT 2;"
    setup, queries = split_queries(sql)
    assert "CREATE VIEW" in setup
    assert queries[1].endswith("SELECT 1;")
    assert queries[2].endswith("SELECT 2;")


def test_both_sql_files_contain_the_benchmark_queries():
    _, pg = split_queries(POSTGRES_SQL.read_text(encoding="utf-8"))
    _, duck = split_queries(DUCKDB_SQL.read_text(encoding="utf-8"))
    assert set(pg) == set(range(1, 11))
    assert set(QUERIES) <= set(duck)


def test_decimal_and_float_results_compare_equal():
    pg = normalise([("Queens", 10, Decimal("33.7"))])
    duck = normalise([("Queens", 10, 33.7)])
    assert same_results(pg, duck)
    assert not same_results(pg, normalise([("Queens", 10, 34.0)]))
