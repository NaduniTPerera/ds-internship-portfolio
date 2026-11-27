import pandas as pd

from quality.profile import profile_dataframe


def test_profile_counts_nulls_distinct_min_max():
    df = pd.DataFrame({
        "fare": [10.0, 20.0, None, 20.0],
        "zone": ["A", "B", "B", None],
    })
    report = profile_dataframe(df).set_index("column")

    assert report.loc["fare", "nulls"] == 1
    assert report.loc["fare", "null_pct"] == 25.0
    assert report.loc["fare", "distinct"] == 2          # 10 and 20; NULL not counted
    assert report.loc["fare", "min"] == "10.00"
    assert report.loc["fare", "max"] == "20.00"
    assert report.loc["zone", "top_values"].startswith("B (50.0%)")


def test_profile_handles_all_null_column():
    report = profile_dataframe(pd.DataFrame({"x": [None, None]})).set_index("column")
    assert report.loc["x", "null_pct"] == 100.0
    assert report.loc["x", "min"] == "NULL"
