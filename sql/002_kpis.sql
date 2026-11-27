-- =====================================================================
-- 002_kpis.sql - 10 business questions on NYC Yellow Taxi, Jan-Jun 2024
-- Uses the star schema from 001_schema.sql (PostgreSQL 16).
--
-- Definitions used throughout:
--   * Revenue      = SUM(total_amount), everything the passenger paid
--                    (fare + tip + tolls + taxes + surcharges). Refunds and
--                    voids have negative amounts and are netted in.
--   * Trip date    = pickup date (fact_trips.pickup_date_key -> dim_date).
--   * Airport trip = pickup OR dropoff in an airport zone
--                    (service_zone 'Airports' = JFK 132, LaGuardia 138;
--                     'EWR' = Newark 1).
--   * Tip %        = tip_amount / fare_amount, only trips with fare > 0.
--                    Cash tips are NOT recorded by TLC, so cash shows ~0%.
--   * Duration     = dropoff - pickup in minutes; only 1 min to 3 hours
--                    is treated as a valid trip.
-- =====================================================================


-- ---------------------------------------------------------------------
-- Q1. Trips and revenue per month
-- ---------------------------------------------------------------------
WITH monthly AS (
    SELECT
        d.year,
        d.month,
        d.month_name,
        COUNT(*)            AS trips,
        SUM(f.total_amount) AS revenue
    FROM fact_trips f
    JOIN dim_date d ON d.date_key = f.pickup_date_key
    GROUP BY d.year, d.month, d.month_name
)
SELECT
    year,
    month,
    month_name,
    trips,
    ROUND(revenue, 2)         AS revenue,
    ROUND(revenue / trips, 2) AS revenue_per_trip
FROM monthly
ORDER BY year, month;


-- ---------------------------------------------------------------------
-- Q2. Top 10 pickup zones by revenue
-- ---------------------------------------------------------------------
WITH zone_revenue AS (
    SELECT
        f.pu_location_id,
        COUNT(*)            AS trips,
        SUM(f.total_amount) AS revenue
    FROM fact_trips f
    GROUP BY f.pu_location_id
),
ranked AS (
    SELECT
        zr.*,
        RANK() OVER (ORDER BY zr.revenue DESC) AS revenue_rank
    FROM zone_revenue zr
)
SELECT
    r.revenue_rank,
    z.zone,
    z.borough,
    r.trips,
    ROUND(r.revenue, 2) AS revenue,
    ROUND(100.0 * r.revenue / SUM(r.revenue) OVER (), 2) AS pct_of_total_revenue
FROM ranked r
JOIN dim_zone z ON z.location_id = r.pu_location_id
ORDER BY r.revenue_rank
LIMIT 10;


-- ---------------------------------------------------------------------
-- Q3. Average tip % by payment type
-- Two views: average of each trip's tip %, and total tips / total fares.
-- ---------------------------------------------------------------------
WITH tipped AS (
    SELECT
        f.payment_type_id,
        f.tip_amount,
        f.fare_amount,
        f.tip_amount / f.fare_amount AS tip_ratio
    FROM fact_trips f
    WHERE f.fare_amount > 0
      AND f.tip_amount >= 0
)
SELECT
    p.payment_type_id,
    p.description                                      AS payment_type,
    COUNT(*)                                           AS trips,
    ROUND(100 * AVG(t.tip_ratio), 2)                   AS avg_tip_pct,
    ROUND(100 * SUM(t.tip_amount) / SUM(t.fare_amount), 2) AS overall_tip_pct,
    ROUND(100.0 * AVG((t.tip_amount > 0)::INT), 2)     AS pct_trips_with_tip
FROM tipped t
JOIN dim_payment_type p ON p.payment_type_id = t.payment_type_id
GROUP BY p.payment_type_id, p.description
ORDER BY p.payment_type_id;


-- ---------------------------------------------------------------------
-- Q4. Busiest hour of the week (heatmap data)
-- 7 days x 24 hours = 168 rows. Plot day_of_week (rows) vs hour (columns)
-- with avg_trips_per_hour as the colour.
-- ---------------------------------------------------------------------
WITH hourly AS (
    SELECT
        d.day_of_week,
        d.day_name,
        EXTRACT(HOUR FROM f.pickup_datetime)::INT AS hour_of_day,
        COUNT(*)                                  AS trips,
        COUNT(DISTINCT d.full_date)               AS days_in_data
    FROM fact_trips f
    JOIN dim_date d ON d.date_key = f.pickup_date_key
    GROUP BY d.day_of_week, d.day_name, EXTRACT(HOUR FROM f.pickup_datetime)
)
SELECT
    day_of_week,
    day_name,
    hour_of_day,
    trips,
    ROUND(trips::NUMERIC / days_in_data, 1)          AS avg_trips_per_hour,
    RANK() OVER (ORDER BY trips DESC)                AS busiest_rank
FROM hourly
ORDER BY day_of_week, hour_of_day;


-- ---------------------------------------------------------------------
-- Q5. Month-over-month revenue growth % (LAG)
-- ---------------------------------------------------------------------
WITH monthly AS (
    SELECT
        d.month,
        d.month_name,
        SUM(f.total_amount) AS revenue
    FROM fact_trips f
    JOIN dim_date d ON d.date_key = f.pickup_date_key
    GROUP BY d.month, d.month_name
)
SELECT
    month,
    month_name,
    ROUND(revenue, 2)                                AS revenue,
    ROUND(LAG(revenue) OVER (ORDER BY month), 2)     AS prev_month_revenue,
    ROUND(
        100 * (revenue - LAG(revenue) OVER (ORDER BY month))
            / LAG(revenue) OVER (ORDER BY month),
        2
    )                                                AS mom_growth_pct
FROM monthly
ORDER BY month;


-- ---------------------------------------------------------------------
-- Q6. Rank of each borough's zones by trips (RANK and DENSE_RANK)
-- RANK leaves gaps after ties (1,2,2,4); DENSE_RANK does not (1,2,2,3).
-- ---------------------------------------------------------------------
WITH zone_trips AS (
    SELECT
        COALESCE(z.borough, 'Outside NYC') AS borough,
        z.zone,
        COUNT(*)                           AS trips
    FROM fact_trips f
    JOIN dim_zone z ON z.location_id = f.pu_location_id
    GROUP BY COALESCE(z.borough, 'Outside NYC'), z.zone
)
SELECT
    borough,
    zone,
    trips,
    RANK()       OVER (PARTITION BY borough ORDER BY trips DESC) AS rank_in_borough,
    DENSE_RANK() OVER (PARTITION BY borough ORDER BY trips DESC) AS dense_rank_in_borough,
    ROUND(100.0 * trips / SUM(trips) OVER (PARTITION BY borough), 2) AS pct_of_borough_trips
FROM zone_trips
ORDER BY borough, rank_in_borough;


-- ---------------------------------------------------------------------
-- Q7. 7-day rolling average of daily trips
-- ---------------------------------------------------------------------
WITH daily AS (
    SELECT
        d.full_date,
        d.day_name,
        COUNT(*) AS trips
    FROM fact_trips f
    JOIN dim_date d ON d.date_key = f.pickup_date_key
    GROUP BY d.full_date, d.day_name
)
SELECT
    full_date,
    day_name,
    trips,
    ROUND(AVG(trips) OVER (
        ORDER BY full_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ), 0) AS rolling_7d_avg_trips,
    -- the first 6 days have fewer than 7 days of history
    COUNT(*) OVER (
        ORDER BY full_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) = 7 AS full_window
FROM daily
ORDER BY full_date;


-- ---------------------------------------------------------------------
-- Q8. Share of airport trips (overall and per airport)
-- ---------------------------------------------------------------------
WITH airport_zones AS (
    SELECT location_id, zone
    FROM dim_zone
    WHERE service_zone IN ('Airports', 'EWR')
),
trip_flags AS (
    SELECT
        f.total_amount,
        pu.zone AS pickup_airport,
        dz.zone AS dropoff_airport
    FROM fact_trips f
    LEFT JOIN airport_zones pu ON pu.location_id = f.pu_location_id
    LEFT JOIN airport_zones dz ON dz.location_id = f.do_location_id
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
        COALESCE(z.borough, 'Outside NYC') AS borough,
        EXTRACT(EPOCH FROM (f.dropoff_datetime - f.pickup_datetime)) / 60.0 AS duration_min
    FROM fact_trips f
    JOIN dim_zone z ON z.location_id = f.pu_location_id
    WHERE f.dropoff_datetime > f.pickup_datetime
)
SELECT
    borough,
    COUNT(*) AS valid_trips,
    ROUND(PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY duration_min)::NUMERIC, 1) AS median_min,
    ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY duration_min)::NUMERIC, 1) AS p25_min,
    ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY duration_min)::NUMERIC, 1) AS p75_min,
    ROUND(AVG(duration_min)::NUMERIC, 1)                                          AS mean_min
FROM durations
WHERE duration_min BETWEEN 1 AND 180
GROUP BY borough
ORDER BY median_min DESC;


-- ---------------------------------------------------------------------
-- Q10. Pickup zones whose revenue dropped more than 20% from January to June
--
-- Finding: total revenue grew ~24% Jan -> Jun, and no zone with at least
-- $10,000 January revenue (131 zones) dropped by 20%. Only 3 small Staten
-- Island zones did, each with a handful of trips, so trip counts are shown
-- to make the small sample size visible.
-- ---------------------------------------------------------------------
WITH zone_month AS (
    SELECT
        f.pu_location_id,
        COUNT(*)            FILTER (WHERE f.source_month = DATE '2024-01-01') AS jan_trips,
        COUNT(*)            FILTER (WHERE f.source_month = DATE '2024-06-01') AS jun_trips,
        SUM(f.total_amount) FILTER (WHERE f.source_month = DATE '2024-01-01') AS jan_revenue,
        SUM(f.total_amount) FILTER (WHERE f.source_month = DATE '2024-06-01') AS jun_revenue
    FROM fact_trips f
    WHERE f.source_month IN (DATE '2024-01-01', DATE '2024-06-01')
    GROUP BY f.pu_location_id
),
change AS (
    SELECT
        pu_location_id,
        jan_trips,
        jun_trips,
        jan_revenue,
        COALESCE(jun_revenue, 0)                                    AS jun_revenue,
        100 * (COALESCE(jun_revenue, 0) - jan_revenue) / jan_revenue AS change_pct
    FROM zone_month
    WHERE jan_revenue > 0
)
SELECT
    z.zone,
    z.borough,
    c.jan_trips,
    c.jun_trips,
    ROUND(c.jan_revenue, 2) AS jan_revenue,
    ROUND(c.jun_revenue, 2) AS jun_revenue,
    ROUND(c.change_pct, 1)  AS change_pct
FROM change c
JOIN dim_zone z ON z.location_id = c.pu_location_id
WHERE c.change_pct < -20
ORDER BY c.change_pct;
