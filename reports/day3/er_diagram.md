# Day 3 - Olist ER diagram

Database `olist` (PostgreSQL 16). DDL: [`sql/olist/001_schema.sql`](../../sql/olist/001_schema.sql).
Loader: [`src/olist/load.py`](../../src/olist/load.py), which reuses the Day 1 helpers in
[`src/ds_intern/db.py`](../../src/ds_intern/db.py).

- **Solid lines** are enforced foreign keys. Every reference exists (0 orphans).
- **Dashed lines** are real relationships that are **not enforced**, because the data
  breaks them (see the notes below).
- `PK` = primary key, `FK` = foreign key. Two `PK` columns in one table form a
  composite key.

```mermaid
erDiagram
    customers ||--o{ orders : "places"
    orders ||--|{ order_items : "contains"
    orders ||--o{ order_payments : "paid by"
    orders ||--o{ order_reviews : "reviewed in"
    products ||--o{ order_items : "sold as"
    sellers ||--o{ order_items : "sells"
    category_translation |o..o{ products : "translates (not enforced)"
    geolocation }o..o{ customers : "zip prefix lookup (not enforced)"
    geolocation }o..o{ sellers : "zip prefix lookup (not enforced)"

    customers {
        text customer_id PK "one per order"
        text customer_unique_id "the real person"
        text customer_zip_code_prefix
        text customer_city
        char2 customer_state
    }
    orders {
        text order_id PK
        text customer_id FK
        text order_status
        timestamp order_purchase_timestamp
        timestamp order_approved_at
        timestamp order_delivered_carrier_date
        timestamp order_delivered_customer_date
        timestamp order_estimated_delivery_date
    }
    order_items {
        text order_id PK, FK
        int order_item_id PK
        text product_id FK
        text seller_id FK
        timestamp shipping_limit_date
        numeric price
        numeric freight_value
    }
    order_payments {
        text order_id PK, FK
        int payment_sequential PK
        text payment_type
        int payment_installments
        numeric payment_value
    }
    order_reviews {
        text review_id PK
        text order_id PK, FK
        smallint review_score "1-5"
        text review_comment_title
        text review_comment_message
        timestamp review_creation_date
        timestamp review_answer_timestamp
    }
    products {
        text product_id PK
        text product_category_name "FK not enforced"
        int product_weight_g
        int product_length_cm
        int product_height_cm
        int product_width_cm
    }
    sellers {
        text seller_id PK
        text seller_zip_code_prefix
        text seller_city
        char2 seller_state
    }
    category_translation {
        text product_category_name PK
        text product_category_name_english
    }
    geolocation {
        bigint geolocation_id PK "surrogate key"
        text geolocation_zip_code_prefix
        float geolocation_lat
        float geolocation_lng
        text geolocation_city
        char2 geolocation_state
    }
```

## Table sizes

| Table | Rows | Grain (one row = ...) |
|---|---:|---|
| `orders` | 99,441 | one order |
| `customers` | 99,441 | one customer *per order* (`customer_unique_id` = the person) |
| `order_items` | 112,650 | one item line in an order |
| `order_payments` | 103,886 | one payment in an order (orders can be split across payments) |
| `order_reviews` | 99,224 | one review of an order |
| `products` | 32,951 | one product |
| `sellers` | 3,095 | one seller |
| `geolocation` | 1,000,163 | one lat/lng point for a zip prefix (many per prefix) |
| `category_translation` | 71 | one Portuguese → English category name |

## Key findings from checking the data

| Finding | Consequence |
|---|---|
| `review_id` repeats 814 times; `(review_id, order_id)` is unique | Composite PK |
| 547 orders have more than one review | The order-level table must pick **one** score per order |
| 2,997 people (`customer_unique_id`) placed more than one order | Their orders are not fully independent (relevant for the statistical tests) |
| 2 categories (13 products) have no English translation | FK not enforced; translations not invented |
| 610 products have no category | Category analysis needs an "unknown" group |
| Zip prefixes repeat in `geolocation`; 278 customer zips are missing from it | Lookup table, not a FK target |
| 8 orders are `delivered` but have no delivery date | Excluded from lateness analysis |
| Zip prefixes have leading zeros (`"01037"`) | Stored as TEXT; 23,995 customer zips start with 0 |
