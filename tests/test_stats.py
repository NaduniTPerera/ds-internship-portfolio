import numpy as np
import pandas as pd
import pytest

from scipy import stats as scipy_stats

from olist.stats import (
    bootstrap_mean_diff,
    chi_square,
    format_p,
    mann_whitney,
    mean_difference,
    welch_t_interval,
)


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


def test_welch_interval_matches_scipy():
    rng = np.random.default_rng(0)
    x, y = rng.normal(2, 1.5, 300), rng.normal(4, 1.0, 900)
    ours = welch_t_interval(x, y)
    ci = scipy_stats.ttest_ind(x, y, equal_var=False).confidence_interval(0.95)
    assert ours["ci_low"] == pytest.approx(ci.low)
    assert ours["ci_high"] == pytest.approx(ci.high)


def test_bootstrap_is_reproducible_and_close_to_t_interval():
    rng = np.random.default_rng(1)
    x, y = rng.integers(1, 6, 2_000), rng.integers(1, 6, 3_000)
    a = bootstrap_mean_diff(x, y, n_resamples=2_000, seed=7)
    b = bootstrap_mean_diff(x, y, n_resamples=2_000, seed=7)
    assert (a["ci_low"], a["ci_high"]) == (b["ci_low"], b["ci_high"])      # same seed
    assert a["ci_low"] < a["estimate"] < a["ci_high"]
    t = welch_t_interval(x, y)
    assert a["std_error"] == pytest.approx(t["std_error"], rel=0.1)        # large samples
    assert len(a["diffs"]) == 2_000
