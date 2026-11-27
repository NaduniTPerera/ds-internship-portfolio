-- =====================================================================
-- sql/olist/002_order_analytics.sql - one row per DELIVERED order, for the
-- Day 3 statistics. Rebuilt from scratch every run (idempotent).
--
-- Definitions:
-- * Population: order_status = 'delivered' AND a customer delivery date exists
--   (lateness is only defined once the order has arrived).
-- * days_late   = delivered date - estimated date, in whole days. The estimate
--                 has no time of day, so arriving on the estimated day = on time.
--                 Negative = early.
-- * is_late     = days_late > 0
-- * review_score: the LATEST review of the order (547 orders have several);
--                 NULL if the order has no review.
-- * price / freight: summed over all items of the order.
-- * seller_state / category: from the order's most expensive item
--                 (ties: lowest order_item_id). n_items / n_sellers kept.
-- * category: English name, else Portuguese name, else 'unknown'.
-- * customer_region: Brazil's 5 official regions (IBGE), from customer_state.
-- =====================================================================

DROP TABLE IF EXISTS order_analytics;

CREATE TABLE order_analytics AS
WITH items AS (
    SELECT order_id,
           COUNT(*)                  AS n_items,
           COUNT(DISTINCT seller_id) AS n_sellers,
           SUM(price)                AS price,
           SUM(freight_value)        AS freight
    FROM order_items
    GROUP BY order_id
),
main_item AS (
    SELECT DISTINCT ON (order_id) order_id, seller_id, product_id
    FROM order_items
    ORDER BY order_id, price DESC, order_item_id
),
latest_review AS (
    SELECT DISTINCT ON (order_id) order_id, review_score
    FROM order_reviews
    ORDER BY order_id, review_answer_timestamp DESC, review_id
)
SELECT
    o.order_id,
    c.customer_unique_id,
    o.order_purchase_timestamp                                         AS purchase_ts,
    o.order_purchase_timestamp::DATE                                   AS purchase_date,
    o.order_estimated_delivery_date::DATE                              AS estimated_delivery_date,
    o.order_delivered_customer_date::DATE                              AS delivered_date,
    o.order_delivered_customer_date::DATE
        - o.order_estimated_delivery_date::DATE                        AS days_late,
    o.order_delivered_customer_date::DATE
        > o.order_estimated_delivery_date::DATE                        AS is_late,
    o.order_delivered_customer_date::DATE
        - o.order_purchase_timestamp::DATE                             AS delivery_days,
    r.review_score,
    i.price,
    i.freight,
    i.n_items,
    i.n_sellers,
    s.seller_state,
    c.customer_state,
    CASE
        WHEN c.customer_state IN ('AC', 'AP', 'AM', 'PA', 'RO', 'RR', 'TO') THEN 'North'
        WHEN c.customer_state IN ('AL', 'BA', 'CE', 'MA', 'PB', 'PE', 'PI', 'RN', 'SE')
            THEN 'Northeast'
        WHEN c.customer_state IN ('DF', 'GO', 'MT', 'MS') THEN 'Center-West'
        WHEN c.customer_state IN ('ES', 'MG', 'RJ', 'SP') THEN 'Southeast'
        WHEN c.customer_state IN ('PR', 'RS', 'SC') THEN 'South'
    END                                                                AS customer_region,
    COALESCE(t.product_category_name_english, p.product_category_name, 'unknown')
                                                                       AS category
FROM orders o
JOIN customers c       ON c.customer_id = o.customer_id
JOIN items i           ON i.order_id = o.order_id
JOIN main_item mi      ON mi.order_id = o.order_id
JOIN sellers s         ON s.seller_id = mi.seller_id
JOIN products p        ON p.product_id = mi.product_id
LEFT JOIN category_translation t ON t.product_category_name = p.product_category_name
LEFT JOIN latest_review r        ON r.order_id = o.order_id
WHERE o.order_status = 'delivered'
  AND o.order_delivered_customer_date IS NOT NULL;

ALTER TABLE order_analytics ADD PRIMARY KEY (order_id);
CREATE INDEX ix_order_analytics_customer ON order_analytics (customer_unique_id);
