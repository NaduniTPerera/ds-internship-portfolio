# Day 2 - Cleaning policy

Input: 20,332,093 raw rows (Jan-Jun 2024). Output: 19,656,373 rows (96.68% kept, 675,720 dropped).
Cleaned files: `data/processed/yellow_tripdata_clean_<YYYY-MM>.parquet` (not in git). Code: `src/quality/clean.py`.

After cleaning, all 16 rules are re-run on the cleaned data, and every **error** rule passes with 0 failures.

| Rule | Severity | Policy | Rows affected | Reason |
|---|---|---|---:|---|
| `vendor_id_valid` | error | **drop** | 0 | Unknown data source; cannot be trusted or joined to dim_vendor. |
| `payment_type_valid` | error | **drop** | 0 | Cannot be joined to dim_payment_type; payment meaning unknown. |
| `zone_ids_valid` | error | **drop** | 0 | Cannot be joined to dim_zone; location unknown. |
| `store_and_fwd_flag_valid` | error | **impute** | 0 | Unimportant technical field; set to NULL instead of losing the trip. Flag column: `flag_store_and_fwd_imputed`. |
| `pickup_in_file_month` | error | **drop** | 149 | Clock or file error (some years 2002-2026); breaks monthly totals. |
| `dropoff_after_pickup` | error | **drop** | 6,177 | Physically impossible; duration and speed cannot be computed. |
| `duration_under_6h` | error | **drop** | 11,349 | Meter left running; recorded time and fare do not describe a real trip. |
| `passenger_count_1_to_6` | error | **impute** | 221,273 | Driver-entered field (0 = not entered). The trip is valid, so set the count to NULL (unknown) and flag it. No fake value is invented. Flag column: `flag_passenger_count_imputed`. |
| `trip_distance_positive` | error | **drop** | 364,322 | No distance recorded (cancelled or meter not used); unusable for fare-per-mile, speed and distance analysis. |
| `speed_plausible` | error | **drop** | 6,715 | Distance or time is wrong, and we cannot tell which one to fix. |
| `fare_amount_non_negative` | error | **drop** | 315,747 | Refunds, voids and disputes: real accounting events, but not trips. |
| `tip_amount_non_negative` | error | **cap** | 705 | Small negative adjustment on an otherwise valid trip; cap at 0. Flag column: `flag_tip_capped`. |
| `total_amount_non_negative` | error | **drop** | 257,431 | Refund or void rows (see fare_amount); not trips. |
| `rate_code_known` | warn | **keep-and-flag** | 214,773 | 99 = 'unknown' is a valid dictionary value; flag for analyses that need the rate code. Flag column: `flag_rate_code_unknown`. |
| `total_matches_components` | warn | **keep-and-flag** | 5,911,741 | Vendor recording convention (vendor 1 counts the congestion surcharge twice, Flex Fare leaves it NULL). The money is correct. Flag column: `flag_total_mismatch`. |
| `flex_fare_fields_present` | warn | **keep-and-flag** | 1,975,985 | Missing by design for Flex Fare trips (payment_type 0); imputing surcharges would invent data. Flag column: `flag_flex_fare_nulls`. |

Rows affected = raw rows failing the rule. One row can fail several rules, so the drop counts add up to more than the 675,720 rows actually dropped.

## Principles

- **Drop only what is impossible and cannot be repaired.** Every dropped row is lost information.
- **Never invent values.** Invalid passenger counts become NULL (unknown), not a guessed number.
- **Explained differences are flagged, not deleted.** Users of the data can filter on the `flag_*` columns if their analysis needs it.
- **The policy is code**, so it is applied the same way every time and can be reviewed.
