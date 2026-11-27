-- =====================================================================
-- 003_duckdb_queries.sql - the 3 heaviest KPI queries (Q4, Q8, Q9 from
-- 002_kpis.sql), run in DuckDB directly on the raw Parquet files.
-- No loading step: DuckDB reads only the columns each query needs.
--
-- Run from the repo root (paths are relative), e.g. with the benchmark:
--   uv run python -m benchmark.compare_engines
--
-- To give exactly the same answers as Postgres, the views apply the same
-- cleaning rule as the loader: keep a trip only if its pickup month equals
-- the month in the file name (drops 149 rows).
-- =====================================================================

CREATE OR REPLACE VIEW trips AS
SELECT *
FROM read_parquet('data/raw/yellow_tripdata_2024-*.parquet', filename = true)
WHERE strftime(tpep_pickup_datetime, '%Y-%m')
      = regexp_extract(filename, '(\d{4}-\d{2})\.parquet', 1);

-- "N/A" means "not applicable"; the Postgres loader stored it as NULL too.
CREATE OR REPLACE VIEW zones AS
SELECT *
FROM read_csv('data/raw/taxi_zone_lookup.csv', header = true, nullstr = ['N/A', '']);


-- ---------------------------------------------------------------------
-- Q4. Busiest hour of the week (heatmap data)
-- ---------------------------------------------------------------------
WITH hourly AS (
    SELECT
        isodow(tpep_pickup_datetime)                    AS day_of_week,
        dayname(tpep_pickup_datetime)                   AS day_name,
        hour(tpep_pickup_datetime)                      AS hour_of_day,
        COUNT(*)                                        AS trips,
        COUNT(DISTINCT CAST(tpep_pickup_datetime AS DATE)) AS days_in_data
    FROM trips
    GROUP BY 1, 2, 3
)
SELECT
    day_of_week,
    day_name,
    hour_of_day,
    trips,
    ROUND(trips / days_in_data, 1)    AS avg_trips_per_hour,
    RANK() OVER (ORDER BY trips DESC) AS busiest_rank
FROM hourly
ORDER BY day_of_week, hour_of_day;


-- ---------------------------------------------------------------------
-- Q8. Share of airport trips (overall and per airport)
-- ---------------------------------------------------------------------
WITH airport_zones AS (
    SELECT LocationID AS location_id, Zone AS zone
    FROM zones
    WHERE service_zone IN ('Airports', 'EWR')
),
trip_flags AS (
    SELECT
        t.total_amount,
        pu.zone AS pickup_airport,
        dz.zone AS dropoff_airport
    FROM trips t
    LEFT JOIN airport_zones pu ON pu.location_id = t.PULocationID
    LEFT JOIN airport_zones dz ON dz.location_id = t.DOLocationID
)
SELECT
    COUNT(*)                                                   AS total_trips,
    COUNT(*) FILTER (WHERE pickup_airport IS NOT NULL
                        OR dropoff_airport IS NOT NULL)        AS airport_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE pickup_airport IS NOT NULL
                                      OR dropoff_airport IS NOT NULL)
          / COUNT(*), 2)                                       AS airport_trip_share_pct,
    ROUND(100.0 * SUM(total_amount) FILTER (WHERE pickup_airport IS NOT NULL
                                               OR dropoff_airport IS NOT NULL)
          / SUM(total_amount), 2)                              AS airport_revenue_share_pct,
    COUNT(*) FILTER (WHERE pickup_airport  = 'JFK Airport'
                        OR dropoff_airport = 'JFK Airport')       AS jfk_trips,
    COUNT(*) FILTER (WHERE pickup_airport  = 'LaGuardia Airport'
                        OR dropoff_airport = 'LaGuardia Airport') AS lga_trips,
    COUNT(*) FILTER (WHERE pickup_airport  = 'Newark Airport'
                        OR dropoff_airport = 'Newark Airport')    AS ewr_trips
FROM trip_flags;


-- ---------------------------------------------------------------------
-- Q9. Median trip duration by pickup borough (PERCENTILE_CONT)
-- ---------------------------------------------------------------------
WITH durations AS (
    SELECT
        COALESCE(z.Borough, 'Outside NYC') AS borough,
        date_diff('second', t.tpep_pickup_datetime, t.tpep_dropoff_datetime) / 60.0
            AS duration_min
    FROM trips t
    JOIN zones z ON z.LocationID = t.PULocationID
    WHERE t.tpep_dropoff_datetime > t.tpep_pickup_datetime
)
-- Results are cast to DECIMAL before ROUND so values exactly on a .x5 boundary
-- round like Postgres NUMERIC (47.15 -> 47.2). As a DOUBLE, 47.15 is stored as
-- 47.1499999... and would round down to 47.1.
SELECT
    borough,
    COUNT(*) AS valid_trips,
    ROUND(CAST(PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY duration_min) AS DECIMAL(18, 6)), 1)
        AS median_min,
    ROUND(CAST(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY duration_min) AS DECIMAL(18, 6)), 1)
        AS p25_min,
    ROUND(CAST(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY duration_min) AS DECIMAL(18, 6)), 1)
        AS p75_min,
    ROUND(CAST(AVG(duration_min) AS DECIMAL(18, 6)), 1)
        AS mean_min
FROM durations
WHERE duration_min BETWEEN 1 AND 180
GROUP BY borough
ORDER BY median_min DESC;
