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

## Progress

| Day | Topic | Status |
|-----|-------|--------|
| 1   | NYC Taxi data warehouse: setup | In progress |
