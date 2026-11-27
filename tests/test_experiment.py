import pytest

from olist.experiment import n_per_group, n_per_group_formula, weeks_needed


def test_statsmodels_matches_textbook_formula():
    # t-test sample size is slightly above the normal approximation
    n = n_per_group(0.1, 1.285)
    approx = n_per_group_formula(0.1, 1.285)
    assert approx <= n <= approx * 1.01


def test_halving_the_effect_needs_four_times_the_sample():
    assert n_per_group(0.05, 1.3) / n_per_group(0.1, 1.3) == pytest.approx(4, rel=0.01)


def test_cohens_d_of_half_needs_64_per_group():
    # well-known reference value: d = 0.5, alpha 0.05, power 0.8 -> 64 per group
    assert n_per_group(0.5, 1.0) == 64


def test_weeks_needed_rounds_up_and_has_a_minimum():
    assert weeks_needed(100, orders_per_week=10_000, scored_share=1.0) == 2   # minimum
    assert weeks_needed(3_000, orders_per_week=1_000, scored_share=1.0) == 6
    assert weeks_needed(3_000, orders_per_week=1_000, scored_share=0.5) == 12
