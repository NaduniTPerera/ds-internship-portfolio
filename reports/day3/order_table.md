# Day 3 - Order-level analytical table

Table `order_analytics` in the `olist` database ([`sql/olist/002_order_analytics.sql`](../../sql/olist/002_order_analytics.sql)), also saved as `data/processed/olist_orders.parquet`. One row = one delivered order.

## Row funnel

| Step | Orders |
|---|---:|
| all orders | 99,441 |
| status = delivered | 96,478 |
| ... and has a delivery date | 96,470 |
| in order_analytics (has items) | 96,470 |
| ... with a review score | 95,824 |

## Headline numbers

- Late orders: 6,534 of 96,470 (6.8%)
- Median days late among late orders: 7; median days early among on-time orders: 13
- Mean review score: on time 4.29, late 2.27
- Orders with more than one seller: 1,275 (1.3%). Seller and category come from the most expensive item.
- Distinct customers (`customer_unique_id`): 93,350 for 96,470 orders

## Column profile (Day 2 profiler)

| column | dtype | rows | nulls | null_pct | distinct | min | max | top_values |
|---|---|---|---|---|---|---|---|---|
| purchase_ts | datetime64[us] | 96,470 | 0 | 0.0 | 95,948 | 2016-09-15 12:16:38 | 2018-08-29 15:00:37 | 2017-11-20 10:59:08 (0.0%), 2017-11-20 11:46:30 (0.0%), 2018-03-31 15:08:21 (0.0%) |
| purchase_date | datetime64[s] | 96,470 | 0 | 0.0 | 612 | 2016-09-15 00:00:00 | 2018-08-29 00:00:00 | 2017-11-24 00:00:00 (1.2%), 2017-11-25 00:00:00 (0.5%), 2017-11-27 00:00:00 (0.4%) |
| estimated_delivery_date | datetime64[s] | 96,470 | 0 | 0.0 | 445 | 2016-10-04 00:00:00 | 2018-10-25 00:00:00 | 2017-12-20 00:00:00 (0.5%), 2018-03-12 00:00:00 (0.5%), 2018-02-14 00:00:00 (0.5%) |
| delivered_date | datetime64[s] | 96,470 | 0 | 0.0 | 645 | 2016-10-11 00:00:00 | 2018-10-17 00:00:00 | 2018-08-27 00:00:00 (0.5%), 2018-08-13 00:00:00 (0.5%), 2018-05-14 00:00:00 (0.4%) |
| days_late | int64 | 96,470 | 0 | 0.0 | 198 | -147 | 188 | -14 (7.4%), -13 (6.2%), -15 (5.5%) |
| is_late | bool | 96,470 | 0 | 0.0 | 2 | False | True | False (93.2%), True (6.8%) |
| delivery_days | int64 | 96,470 | 0 | 0.0 | 144 | 0 | 210 | 7 (7.8%), 8 (7.4%), 6 (6.7%) |
| review_score | Int64 | 96,470 | 646 | 0.67 | 5 | 1 | 5 | 5 (58.8%), 4 (19.6%), 1 (9.7%) |
| price | float64 | 96,470 | 0 | 0.0 | 7,435 | 0.85 | 13,440.00 | 59.90 (1.7%), 69.90 (1.6%), 49.90 (1.4%) |
| freight | float64 | 96,470 | 0 | 0.0 | 7,476 | 0.00 | 1,794.96 | 15.10 (3.0%), 7.78 (1.9%), 14.10 (1.5%) |
| n_items | int64 | 96,470 | 0 | 0.0 | 17 | 1 | 21 | 1 (90.0%), 2 (7.7%), 3 (1.4%) |
| n_sellers | int64 | 96,470 | 0 | 0.0 | 5 | 1 | 5 | 1 (98.7%), 2 (1.3%), 3 (0.1%) |
| seller_state | str | 96,470 | 0 | 0.0 | 22 | AM | SP | SP (70.9%), MG (7.9%), PR (7.7%) |
| customer_state | str | 96,470 | 0 | 0.0 | 27 | AC | TO | SP (42.0%), RJ (12.8%), MG (11.8%) |
| customer_region | str | 96,470 | 0 | 0.0 | 5 | Center-West | Southeast | Southeast (68.6%), South (14.3%), Northeast (9.4%) |
| category | str | 96,470 | 0 | 0.0 | 74 | agro_industry_and_commerce | watches_gifts | bed_bath_table (9.5%), health_beauty (8.9%), sports_leisure (7.8%) |
