-- =====================================================================
-- 004_index_explain.sql - effect of one index, shown with EXPLAIN ANALYZE
--
-- Query: daily trips and revenue for one week (a typical dashboard filter).
-- It needs ~830k of the 20M rows (~4%).
--
-- Why a COVERING index (pickup_datetime) INCLUDE (total_amount):
-- * First attempt: a plain index on (pickup_datetime). The planner IGNORED
--   it for this query and kept the parallel sequential scan. The rows are
--   only loosely stored in time order (pg_stats correlation = 0.39), so
--   fetching 830k rows through the index means random reads all over the
--   table, which Postgres estimated to be slower than one full scan.
--   (It did use the plain index for a 1-day window, ~0.6% of rows.)
-- * The covering index also stores total_amount, so the query can be
--   answered from the index alone (Index Only Scan) without touching the
--   table. VACUUM keeps the visibility map current, which index-only
--   scans need.
--
-- Note: an index does NOT help the full-table KPI queries (Q4, Q8, Q9):
-- they read every row, and a sequential scan is the fastest way to do that.
--
-- Run (output saved as the evidence for the report):
--   docker exec -i nyc_taxi_pg psql -U postgres -d nyc_taxi < sql/004_index_explain.sql
-- =====================================================================

\timing on

-- Start from a clean state so the "before" plan really has no index.
DROP INDEX IF EXISTS ix_fact_trips_pickup_datetime;

-- Warm-up run, so "before" and "after" both read from a warm cache.
SELECT COUNT(*) FROM fact_trips
WHERE pickup_datetime >= '2024-03-11' AND pickup_datetime < '2024-03-18';

\echo '==================== BEFORE (no index) ===================='
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    pickup_datetime::DATE AS trip_date,
    COUNT(*)              AS trips,
    SUM(total_amount)     AS revenue
FROM fact_trips
WHERE pickup_datetime >= '2024-03-11'
  AND pickup_datetime <  '2024-03-18'
GROUP BY 1
ORDER BY 1;

\echo '==================== CREATE INDEX ===================='
CREATE INDEX ix_fact_trips_pickup_datetime
    ON fact_trips (pickup_datetime) INCLUDE (total_amount);
VACUUM ANALYZE fact_trips;
SELECT pg_size_pretty(pg_relation_size('ix_fact_trips_pickup_datetime')) AS index_size;

\echo '==================== AFTER (with index) ===================='
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    pickup_datetime::DATE AS trip_date,
    COUNT(*)              AS trips,
    SUM(total_amount)     AS revenue
FROM fact_trips
WHERE pickup_datetime >= '2024-03-11'
  AND pickup_datetime <  '2024-03-18'
GROUP BY 1
ORDER BY 1;
