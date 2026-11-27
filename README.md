# DS Internship Portfolio

Work from an 8-day data science internship. It starts with a NYC Taxi trip data warehouse.

## Project structure

```
data/
  raw/          # downloaded source data (not committed)
  processed/    # cleaned / transformed data (not committed)
docker/         # Docker / docker-compose files for the warehouse
notebooks/      # exploration and analysis notebooks
reports/
  figures/      # charts used in reports
sql/            # schema and query files
src/ds_intern/  # reusable Python code
tests/          # pytest tests
```

## Setup

Requirements: [uv](https://docs.astral.sh/uv/), Python 3.12, Docker Desktop.

```bash
# install dependencies into .venv
uv sync

# create your local config, then edit the values
cp .env.example .env

# run tests
uv run pytest
```

## Database (PostgreSQL 16 in Docker)

```bash
# start (data is stored in the named volume ds-intern_pgdata)
docker compose --env-file .env -f docker/docker-compose.yml up -d

# check status - should say "(healthy)"
docker ps --filter name=nyc_taxi_pg

# stop (data is kept)
docker compose --env-file .env -f docker/docker-compose.yml down
```

Connection: `localhost:5433`, database `nyc_taxi`, user and password from `.env`.
Host port 5433 is used so it does not clash with a local Postgres on 5432.

## Progress

| Day | Topic | Status |
|-----|-------|--------|
| 1   | NYC Taxi data warehouse: repo scaffold, Postgres 16 in Docker, download script, star schema | In progress |

## Day 1: star schema

![Star schema](reports/day1_schema.png)

`fact_trips` (one row per trip) links to `dim_vendor`, `dim_payment_type`, `dim_date` and
`dim_zone`. `dim_zone` is used twice, for pickup and dropoff. DDL: [`sql/001_schema.sql`](sql/001_schema.sql).

```bash
# download raw data (skips files that already exist)
uv run python -m ingest.download

# create the tables (safe to re-run)
docker exec -i nyc_taxi_pg psql -U postgres -d nyc_taxi < sql/001_schema.sql

# load zones + all six months (about 10 minutes; safe to re-run)
uv run python -m ingest.load_postgres
# or reload a single month
uv run python -m ingest.load_postgres --months 2024-03
```

The loader reads each Parquet file in batches of 500,000 rows and streams them into
Postgres with `COPY`. Each month is loaded in one transaction: delete that month's rows,
insert the new ones, and record the run in `load_batch`. Re-running replaces a month
instead of duplicating it. If a run fails halfway, the transaction rolls back.
Trips whose pickup time falls outside the file's month are dropped and counted
in `load_batch.rows_dropped`.
