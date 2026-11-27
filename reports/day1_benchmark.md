# Day 1 - Postgres vs DuckDB runtimes

Run on 2026-11-27. Median of 3 timed runs after 1 warm-up run.

| Query | Question | Postgres 16 (s) | DuckDB on Parquet (s) | Speed-up | Same result |
|---|---|---:|---:|---:|:---:|
| Q4 | Busiest hour of week (heatmap) | 33.70 | 0.99 | 34x | yes |
| Q8 | Share of airport trips | 22.32 | 1.87 | 12x | yes |
| Q9 | Median trip duration by borough | 46.20 | 3.15 | 15x | yes |

Setup:
- Postgres 16 in Docker (WSL2), table `fact_trips` with 20,331,944 rows, default settings, no extra indexes.
- DuckDB 2.0.1 in-process, reading the 6 raw Parquet files directly (no load step), same cleaning rule as the loader.
- Machine: Windows 11, 12 logical CPUs.

Queries: Postgres versions in `sql/002_kpis.sql`, DuckDB versions in `sql/003_duckdb_queries.sql`.
