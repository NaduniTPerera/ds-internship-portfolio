-- =====================================================================
-- sql/olist/001_schema.sql - Olist Brazilian e-commerce (9 tables), PostgreSQL 16
-- Database: olist (same Postgres server as Day 1). Safe to re-run.
--
-- Keys were chosen after checking the data (uniqueness + orphan counts):
-- * PK on every table; composite PKs where an id is only unique per order.
-- * order_reviews.review_id is NOT unique on its own (814 duplicates), so the
--   PK is (review_id, order_id). 547 orders have more than one review.
-- * FKs are enforced wherever every reference exists (0 orphans).
-- * NOT enforced, documented instead:
--   - products.product_category_name -> category_translation: 2 categories
--     ('pc_gamer', 'portateis_cozinha_e_preparadores_de_alimentos', 13 products)
--     have no translation. We do not invent translations.
--   - customers/sellers zip prefix -> geolocation: zip prefixes repeat in
--     geolocation (many lat/lng points per prefix) and 278 customer zips are
--     missing, so geolocation is a lookup table, not a key target.
-- * Zip prefixes are TEXT, not numbers: "01037" must keep its leading zero.
-- * Column names keep the source spelling (incl. the "lenght" typos) so they
--   match the Kaggle documentation.
-- =====================================================================

CREATE TABLE IF NOT EXISTS category_translation (
    product_category_name          TEXT PRIMARY KEY,
    product_category_name_english  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    customer_id               TEXT PRIMARY KEY,      -- one per order
    customer_unique_id        TEXT NOT NULL,         -- the real person (2,997 have >1 order)
    customer_zip_code_prefix  TEXT NOT NULL,
    customer_city             TEXT NOT NULL,
    customer_state            CHAR(2) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_customers_unique_id ON customers (customer_unique_id);

CREATE TABLE IF NOT EXISTS sellers (
    seller_id               TEXT PRIMARY KEY,
    seller_zip_code_prefix  TEXT NOT NULL,
    seller_city             TEXT NOT NULL,
    seller_state            CHAR(2) NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    product_id                  TEXT PRIMARY KEY,
    product_category_name       TEXT,                -- NULL for 610 products; FK not enforced
    product_name_lenght         INTEGER,
    product_description_lenght  INTEGER,
    product_photos_qty          INTEGER,
    product_weight_g            INTEGER,
    product_length_cm           INTEGER,
    product_height_cm           INTEGER,
    product_width_cm            INTEGER
);

CREATE TABLE IF NOT EXISTS geolocation (
    geolocation_id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    geolocation_zip_code_prefix  TEXT NOT NULL,
    geolocation_lat              DOUBLE PRECISION NOT NULL,
    geolocation_lng              DOUBLE PRECISION NOT NULL,
    geolocation_city             TEXT NOT NULL,
    geolocation_state            CHAR(2) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_geolocation_zip ON geolocation (geolocation_zip_code_prefix);

CREATE TABLE IF NOT EXISTS orders (
    order_id                       TEXT PRIMARY KEY,
    customer_id                    TEXT NOT NULL REFERENCES customers (customer_id),
    order_status                   TEXT NOT NULL,
    order_purchase_timestamp       TIMESTAMP NOT NULL,
    order_approved_at              TIMESTAMP,
    order_delivered_carrier_date   TIMESTAMP,
    order_delivered_customer_date  TIMESTAMP,        -- NULL if not delivered
    order_estimated_delivery_date  TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS order_items (
    order_id             TEXT NOT NULL REFERENCES orders (order_id),
    order_item_id        INTEGER NOT NULL,            -- 1, 2, 3 ... within the order
    product_id           TEXT NOT NULL REFERENCES products (product_id),
    seller_id            TEXT NOT NULL REFERENCES sellers (seller_id),
    shipping_limit_date  TIMESTAMP NOT NULL,
    price                NUMERIC(10, 2) NOT NULL,
    freight_value        NUMERIC(10, 2) NOT NULL,
    PRIMARY KEY (order_id, order_item_id)
);
CREATE INDEX IF NOT EXISTS ix_order_items_product ON order_items (product_id);
CREATE INDEX IF NOT EXISTS ix_order_items_seller ON order_items (seller_id);

CREATE TABLE IF NOT EXISTS order_payments (
    order_id              TEXT NOT NULL REFERENCES orders (order_id),
    payment_sequential    INTEGER NOT NULL,
    payment_type          TEXT NOT NULL,
    payment_installments  INTEGER NOT NULL,
    payment_value         NUMERIC(10, 2) NOT NULL,
    PRIMARY KEY (order_id, payment_sequential)
);

CREATE TABLE IF NOT EXISTS order_reviews (
    review_id                TEXT NOT NULL,
    order_id                 TEXT NOT NULL REFERENCES orders (order_id),
    review_score             SMALLINT NOT NULL CHECK (review_score BETWEEN 1 AND 5),
    review_comment_title     TEXT,
    review_comment_message   TEXT,
    review_creation_date     TIMESTAMP NOT NULL,
    review_answer_timestamp  TIMESTAMP NOT NULL,
    PRIMARY KEY (review_id, order_id)
);
CREATE INDEX IF NOT EXISTS ix_order_reviews_order ON order_reviews (order_id);
