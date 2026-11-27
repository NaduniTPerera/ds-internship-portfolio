-- =====================================================================
-- 001_schema.sql - NYC Yellow Taxi star schema (PostgreSQL 16)
--
-- fact_trips (one row per trip) in the centre, four dimensions around it:
--   dim_vendor, dim_payment_type, dim_zone (used twice: pickup + dropoff),
--   dim_date.
-- Diagram: reports/day1_schema.png
--
-- Safe to re-run: CREATE ... IF NOT EXISTS and INSERT ... ON CONFLICT.
-- Run:  psql -h localhost -p 5433 -U postgres -d nyc_taxi -f sql/001_schema.sql
-- =====================================================================


-- ---------------------------------------------------------------------
-- dim_vendor: the technology provider that recorded the trip.
-- Codes from the TLC Yellow Taxi data dictionary.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_vendor (
    vendor_id    SMALLINT    PRIMARY KEY,
    vendor_name  TEXT        NOT NULL
);

INSERT INTO dim_vendor (vendor_id, vendor_name) VALUES
    (1, 'Creative Mobile Technologies, LLC'),
    (2, 'Curb Mobility, LLC'),
    (6, 'Myle Technologies Inc'),
    (7, 'Helix')
ON CONFLICT (vendor_id) DO NOTHING;


-- ---------------------------------------------------------------------
-- dim_payment_type: how the passenger paid.
-- Codes from the TLC Yellow Taxi data dictionary.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_payment_type (
    payment_type_id  SMALLINT  PRIMARY KEY,
    description      TEXT      NOT NULL
);

INSERT INTO dim_payment_type (payment_type_id, description) VALUES
    (0, 'Flex Fare trip'),
    (1, 'Credit card'),
    (2, 'Cash'),
    (3, 'No charge'),
    (4, 'Dispute'),
    (5, 'Unknown'),
    (6, 'Voided trip')
ON CONFLICT (payment_type_id) DO NOTHING;


-- ---------------------------------------------------------------------
-- dim_zone: TLC taxi zones (loaded from data/raw/taxi_zone_lookup.csv
-- by src/ingest/load_postgres.py). 265 rows; 264/265 are "Unknown"/"N/A".
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_zone (
    location_id   SMALLINT  PRIMARY KEY,
    borough       TEXT,
    zone          TEXT,
    service_zone  TEXT
);


-- ---------------------------------------------------------------------
-- dim_date: one row per calendar day of 2024.
-- date_key is YYYYMMDD as an integer (e.g. 20240115): small, sortable,
-- and readable.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_date (
    date_key     INTEGER   PRIMARY KEY,
    full_date    DATE      NOT NULL UNIQUE,
    year         SMALLINT  NOT NULL,
    quarter      SMALLINT  NOT NULL,
    month        SMALLINT  NOT NULL,
    month_name   TEXT      NOT NULL,
    day          SMALLINT  NOT NULL,
    day_of_week  SMALLINT  NOT NULL,   -- ISO: 1 = Monday ... 7 = Sunday
    day_name     TEXT      NOT NULL,
    is_weekend   BOOLEAN   NOT NULL
);

INSERT INTO dim_date
SELECT
    TO_CHAR(d, 'YYYYMMDD')::INTEGER         AS date_key,
    d::DATE                                 AS full_date,
    EXTRACT(YEAR    FROM d)::SMALLINT       AS year,
    EXTRACT(QUARTER FROM d)::SMALLINT       AS quarter,
    EXTRACT(MONTH   FROM d)::SMALLINT       AS month,
    TRIM(TO_CHAR(d, 'Month'))               AS month_name,
    EXTRACT(DAY     FROM d)::SMALLINT       AS day,
    EXTRACT(ISODOW  FROM d)::SMALLINT       AS day_of_week,
    TRIM(TO_CHAR(d, 'Day'))                 AS day_name,
    EXTRACT(ISODOW  FROM d) IN (6, 7)       AS is_weekend
FROM generate_series('2024-01-01'::DATE, '2024-12-31'::DATE, INTERVAL '1 day') AS d
ON CONFLICT (date_key) DO NOTHING;


-- ---------------------------------------------------------------------
-- fact_trips: one row per yellow taxi trip.
-- Money uses NUMERIC(10,2): exact to the cent (FLOAT gives rounding errors).
-- source_month = the monthly file the row came from; the loader deletes
-- and reloads one month at a time, so re-running never duplicates rows.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_trips (
    trip_id                BIGINT        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- foreign keys to the dimensions
    vendor_id              SMALLINT      NOT NULL REFERENCES dim_vendor (vendor_id),
    pickup_date_key        INTEGER       NOT NULL REFERENCES dim_date (date_key),
    payment_type_id        SMALLINT      NOT NULL REFERENCES dim_payment_type (payment_type_id),
    pu_location_id         SMALLINT      NOT NULL REFERENCES dim_zone (location_id),
    do_location_id         SMALLINT      NOT NULL REFERENCES dim_zone (location_id),

    -- trip details
    pickup_datetime        TIMESTAMP     NOT NULL,
    dropoff_datetime       TIMESTAMP     NOT NULL,
    passenger_count        SMALLINT,               -- NULL for Flex Fare trips
    trip_distance          NUMERIC(10,2) NOT NULL, -- miles
    rate_code_id           SMALLINT,               -- 99 = unknown; NULL for Flex Fare
    store_and_fwd_flag     CHAR(1),                -- 'Y' / 'N'

    -- money (USD)
    fare_amount            NUMERIC(10,2) NOT NULL,
    extra                  NUMERIC(10,2) NOT NULL,
    mta_tax                NUMERIC(10,2) NOT NULL,
    tip_amount             NUMERIC(10,2) NOT NULL,
    tolls_amount           NUMERIC(10,2) NOT NULL,
    improvement_surcharge  NUMERIC(10,2) NOT NULL,
    congestion_surcharge   NUMERIC(10,2),
    airport_fee            NUMERIC(10,2),
    total_amount           NUMERIC(10,2) NOT NULL,

    -- load bookkeeping
    source_month           DATE          NOT NULL  -- first day of the file's month
);

-- Needed so "delete this month, then reload it" is fast.
CREATE INDEX IF NOT EXISTS ix_fact_trips_source_month ON fact_trips (source_month);
