# Day 1 - One index, EXPLAIN ANALYZE before and after

Script: [`sql/004_index_explain.sql`](../sql/004_index_explain.sql).
Full plans: [`day1_explain_analyze.txt`](day1_explain_analyze.txt).

**Query:** daily trips and revenue for one week (2024-03-11 to 2024-03-17), a typical
dashboard filter. It matches 830,981 of the 20,331,944 trips (about 4%).

**Index:**

```sql
CREATE INDEX ix_fact_trips_pickup_datetime
    ON fact_trips (pickup_datetime) INCLUDE (total_amount);
```

| | Before (no index) | After (covering index) |
|---|---:|---:|
| Plan | Parallel Seq Scan on `fact_trips` | Index Only Scan using `ix_fact_trips_pickup_datetime` |
| Pages read from disk | 389,542 | 3,187 |
| Heap (table) fetches | whole table scanned | 0 |
| Execution time | 23.6 s | 1.0 s (about 23x faster) |
| Extra disk space | - | 611 MB |

## What I learned

1. **A plain index on `pickup_datetime` was not used for this query.** The planner kept
   the full parallel scan. The rows are only loosely stored in time order (`pg_stats`
   correlation 0.39), so reading 4% of the rows through the index would mean random reads
   across most of the table. Postgres estimated that to be slower than one sequential scan.
   It *did* use the plain index for a 1-day window (about 0.6% of rows).
2. **A covering index solved it.** With `INCLUDE (total_amount)`, every column the query
   needs is inside the index, so Postgres answers from the index alone (Index Only Scan,
   0 heap fetches). An index-only scan needs an up-to-date visibility map, so the script
   runs `VACUUM ANALYZE` after creating the index.
3. **Indexes do not help full-table aggregations.** Q4, Q8 and Q9 in `sql/002_kpis.sql` read
   every row, and a sequential scan is already the fastest way to do that. For these
   queries, a columnar engine (DuckDB on Parquet) was 12-34x faster. See
   [`day1_benchmark.md`](day1_benchmark.md).
4. **Indexes have a cost.** This one uses 611 MB and slows down loading, because every
   inserted row must also be added to the index.
