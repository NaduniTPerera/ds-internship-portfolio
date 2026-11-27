# Day 2 - Validation report (raw data, Jan-Jun 2024)

Rows checked: 20,332,093. Rules: 16 (13 error, 3 warn). Rule definitions: `src/quality/schema.py`.

- **error**: the row is wrong or impossible. Counts toward the CI failure rate.
- **warn**: suspicious or explained by how the data is recorded. Reported only.

| Rule | Severity | Description | Rows failing | % failing | Example bad row |
|---|---|---|---:|---:|---|
| `vendor_id_valid` | error | VendorID is a code from the data dictionary (1, 2, 6, 7) | 0 | 0.000 |  |
| `payment_type_valid` | error | payment_type is a dictionary code (0-6) | 0 | 0.000 |  |
| `zone_ids_valid` | error | PU/DO LocationID are valid zones (1-265) | 0 | 0.000 |  |
| `store_and_fwd_flag_valid` | error | store_and_fwd_flag is Y or N (NULL allowed) | 0 | 0.000 |  |
| `pickup_in_file_month` | error | pickup time falls inside the file's month | 149 | 0.001 | tpep_pickup_datetime=2023-12-31 23:56:46 |
| `dropoff_after_pickup` | error | dropoff is strictly after pickup | 6,177 | 0.030 | tpep_pickup_datetime=2024-01-01 00:14:29, tpep_dropoff_datetime=2024-01-01 00:14:29 |
| `duration_under_6h` | error | trip duration is less than 6 hours | 11,349 | 0.056 | tpep_pickup_datetime=2024-01-01 00:39:11, tpep_dropoff_datetime=2024-01-02 00:34:19 |
| `passenger_count_1_to_6` | error | passenger_count between 1 and 6 (NULL allowed) | 221,273 | 1.088 | passenger_count=0 |
| `trip_distance_positive` | error | trip_distance is greater than 0 miles | 364,322 | 1.792 | trip_distance=0 |
| `speed_plausible` | error | average speed is at most 80 mph | 6,715 | 0.033 | trip_distance=2.3, tpep_pickup_datetime=2024-01-01 00:26:02, tpep_dropoff_datetime=2024-01-01 00:26:21 |
| `fare_amount_non_negative` | error | fare_amount >= 0 | 315,747 | 1.553 | fare_amount=-13.5 |
| `tip_amount_non_negative` | error | tip_amount >= 0 | 705 | 0.003 | tip_amount=-8.18 |
| `total_amount_non_negative` | error | total_amount >= 0 | 257,431 | 1.266 | total_amount=-18.5 |
| `rate_code_known` | warn | RatecodeID is 1-6 (99 = unknown; NULL allowed) | 214,773 | 1.056 | RatecodeID=99 |
| `total_matches_components` | warn | total_amount = sum of fare, extra, taxes, tip, tolls, surcharges, fees (within $0.01) | 5,911,741 | 29.076 | VendorID=1, total_amount=18.75, fare_amount=10, extra=3.5, congestion_surcharge=2.5 |
| `flex_fare_fields_present` | warn | passenger_count, RatecodeID, store_and_fwd_flag, congestion_surcharge, Airport_fee are not NULL | 1,975,985 | 9.719 | payment_type=0, passenger_count=NULL, RatecodeID=NULL, store_and_fwd_flag=NULL, congestion_surcharge=NULL, Airport_fee=NULL |

## Rows failing at least one error rule, per month

| Month | Rows | Rows failing | % failing |
|---|---:|---:|---:|
| 2024-01 | 2,964,624 | 128,085 | 4.32 |
| 2024-02 | 3,007,526 | 141,234 | 4.70 |
| 2024-03 | 3,582,628 | 183,800 | 5.13 |
| 2024-04 | 3,514,289 | 140,408 | 4.00 |
| 2024-05 | 3,723,833 | 146,414 | 3.93 |
| 2024-06 | 3,539,193 | 147,452 | 4.17 |

## Root causes found while investigating

- **`total_matches_components` (29%) is a recording difference, not wrong money.**
  Vendor 1 includes the $2.50 congestion surcharge inside `extra` *and* in
  `congestion_surcharge`, so adding all components counts it twice (difference
  -$2.50, about 3.8M trips). Flex Fare trips (payment_type 0, mostly vendor 2) include
  $2.50 in the total but leave `congestion_surcharge` NULL (difference +$2.50). Almost
  every mismatch is exactly +/-$2.50, +/-$1.75 (airport fee) or a combination.
- **`flex_fare_fields_present`**: Flex Fare trips (payment_type 0) never record
  passenger count, rate code, store-and-forward flag or the surcharges. This is
  by design, so it is a warning, not an error.
- **Negative `fare_amount` / `total_amount`**: refunds, voids and disputes are
  recorded as negative rows. They are real events, but they are not trips.
- **`trip_distance` = 0 and `passenger_count` = 0**: driver-entered or meter
  values that were never filled in (cancelled trips, meter not reset).
- **`pickup_in_file_month`**: 149 rows, the same 149 the Day 1 loader dropped.
