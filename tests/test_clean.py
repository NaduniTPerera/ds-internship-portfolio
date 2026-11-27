from datetime import date

import pandas as pd

from quality.clean import POLICY, clean_month, verify_clean
from quality.schema import RULES
from tests.helpers import trip, trips_df

JAN = date(2024, 1, 1)


def test_every_rule_has_a_policy():
    assert {r.name for r in RULES} == set(POLICY)
    assert {p.action for p in POLICY.values()} <= {"drop", "cap", "impute", "keep-and-flag"}


def test_policy_drops_imputes_caps_and_flags():
    raw = trips_df([
        trip(),                                   # good -> kept unchanged
        trip(fare_amount=-5.0, total_amount=-5.0),  # refund -> dropped
        trip(passenger_count=0.0),                # -> kept, count imputed to NULL
        trip(tip_amount=-1.0, total_amount=23.0),   # -> kept, tip capped at 0
    ])
    clean, affected = clean_month(raw, JAN)

    assert len(clean) == 3
    assert affected["_dropped_total"] == 1
    assert pd.isna(clean.loc[1, "passenger_count"])
    assert clean.loc[1, "flag_passenger_count_imputed"]
    assert clean.loc[2, "tip_amount"] == 0.0
    assert clean.loc[2, "flag_tip_capped"]
    assert not clean.loc[0, ["flag_tip_capped", "flag_passenger_count_imputed"]].any()

    verify_clean(clean, JAN)   # raises if any error rule still fails
