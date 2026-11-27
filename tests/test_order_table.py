import pandas as pd
import pytest

from olist.order_table import validate


def orders(**changes) -> pd.DataFrame:
    base = {
        "order_id": ["a", "b"],
        "days_late": [-5, 3],
        "is_late": [False, True],
        "customer_region": ["Southeast", "North"],
        "review_score": pd.array([5, None], dtype="Int64"),
        "delivery_days": [7, 20],
    }
    base.update(changes)
    return pd.DataFrame(base)


def test_valid_table_passes():
    validate(orders())


@pytest.mark.parametrize("changes, message", [
    ({"order_id": ["a", "a"]}, "not unique"),
    ({"is_late": [True, True]}, "is_late"),
    ({"customer_region": ["Southeast", None]}, "region"),
    ({"review_score": pd.array([6, None], dtype="Int64")}, "review_score"),
    ({"delivery_days": [-1, 20]}, "before purchase"),
])
def test_broken_table_is_rejected(changes, message):
    with pytest.raises(ValueError, match=message):
        validate(orders(**changes))
