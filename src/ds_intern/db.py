"""Reusable Postgres helpers, shared by every loader in this project.

Originally part of the Day 1 taxi loader (src/ingest/load_postgres.py); moved here
so the Day 3 Olist loader uses exactly the same, already-tested code path:

    connect()          open a connection (any database on the server)
    ensure_database()  create a database if it does not exist
    run_sql_file()     execute a .sql file (e.g. CREATE TABLE ... IF NOT EXISTS)
    copy_arrow()       bulk-load a pyarrow Table with COPY (much faster than INSERT)
"""

import io
import logging
from pathlib import Path

import psycopg
import pyarrow as pa
import pyarrow.csv as pacsv
from psycopg import sql

from ds_intern.config import pg_params

logger = logging.getLogger(__name__)

_CSV_OPTIONS = pacsv.WriteOptions(include_header=False)


def connect(dbname: str | None = None, autocommit: bool = True) -> psycopg.Connection:
    """Connect to Postgres. autocommit=True; use `with conn.transaction():` for atomic work."""
    return psycopg.connect(**pg_params(dbname), autocommit=autocommit)


def ensure_database(dbname: str) -> bool:
    """Create the database if it does not exist. Returns True if it was created."""
    with connect() as conn:   # connect to the default database to run CREATE DATABASE
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s",
                              (dbname,)).fetchone()
        if exists:
            return False
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
        logger.info("Created database %s", dbname)
        return True


def run_sql_file(conn: psycopg.Connection, path: Path) -> None:
    """Execute every statement in a .sql file (no psql meta-commands)."""
    conn.execute(path.read_text(encoding="utf-8"))


def copy_arrow(cur: psycopg.Cursor, table: str, data: pa.Table,
               columns: list[str] | None = None) -> int:
    """Bulk-load a pyarrow Table into `table` with COPY ... FROM STDIN (CSV).

    columns: target column names in the same order as `data` (default: data's names).
    NULLs are written as empty unquoted fields, which COPY CSV reads as NULL.
    Returns the number of rows copied.
    """
    columns = columns or data.column_names
    statement = sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT csv)").format(
        sql.Identifier(*table.split(".")),
        sql.SQL(", ").join(sql.Identifier(c) for c in columns),
    )
    buffer = io.BytesIO()
    pacsv.write_csv(data, buffer, _CSV_OPTIONS)
    with cur.copy(statement) as copy:
        copy.write(buffer.getvalue())
    return data.num_rows
