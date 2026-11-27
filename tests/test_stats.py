import numpy as np
import pandas as pd
import pytest

from olist.stats import chi_square, format_p, mann_whitney, mean_difference


def test_rank_biserial_extremes_and_zero():
    low, high = [1, 1, 2], [4, 5, 5]
    assert mann_whitney(low, high)["rank_biserial"] == pytest.approx(-1.0)  # x always lower
    assert mann_whitney(high, low)["rank_biserial"] == pytest.approx(1.0)
    same = mann_whitney([1, 2, 3, 4], [1, 2, 3, 4])
    assert same["rank_biserial"] == pytest.approx(0.0)
    assert same["cles"] == pytest.approx(0.5)


def test_cramers_v_perfect_and_none():
    perfect = pd.DataFrame([[50, 0], [0, 50]])
    assert chi_square(perfect)["cramers_v"] == pytest.approx(1.0)
    none = pd.DataFrame([[25, 25], [25, 25]])
    result = chi_square(none)
    assert result["cramers_v"] == pytest.approx(0.0)
    assert result["p_value"] == pytest.approx(1.0)
    assert result["cells_expected_below_5"] == 0


def test_mean_difference():
    result = mean_difference(np.array([2.0, 4.0]), np.array([5.0, 5.0]))
    assert result["diff"] == pytest.approx(-2.0)
    assert result["median_x"] == 3.0


def test_format_p():
    assert format_p(0.0) == "< 1e-300"
    assert format_p(0.0312) == "0.0312"
    assert format_p(1.5e-12) == "1.50e-12"
