"""Reusable statistics helpers for Day 3 (tests, effect sizes, intervals).

Each function returns a small dict so results can be printed, tabulated or tested.
Effect-size conventions:
- rank-biserial r = 2 * U_x / (n_x * n_y) - 1, in [-1, 1].
  Negative r: values in x tend to be LOWER than in y.
- common-language effect size (CLES) = U_x / (n_x * n_y)
  = P(random x > random y) + 0.5 * P(tie).
- Cramer's V = sqrt(chi2 / (n * (min(rows, cols) - 1))), in [0, 1].
"""

import numpy as np
import pandas as pd
from scipy import stats


def mann_whitney(x: np.ndarray, y: np.ndarray) -> dict:
    """Two-sided Mann-Whitney U test of x vs y, with rank-biserial effect size."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    result = stats.mannwhitneyu(x, y, alternative="two-sided", method="asymptotic")
    n_x, n_y = len(x), len(y)
    cles = result.statistic / (n_x * n_y)
    return {
        "U": float(result.statistic),
        "p_value": float(result.pvalue),
        "n_x": n_x,
        "n_y": n_y,
        "cles": float(cles),
        "rank_biserial": float(2 * cles - 1),
    }


def chi_square(table: pd.DataFrame) -> dict:
    """Chi-square test of independence on a contingency table, with Cramer's V."""
    observed = np.asarray(table, dtype=float)
    chi2, p_value, dof, expected = stats.chi2_contingency(observed, correction=False)
    n = observed.sum()
    k = min(observed.shape) - 1
    return {
        "chi2": float(chi2),
        "p_value": float(p_value),
        "dof": int(dof),
        "n": int(n),
        "cramers_v": float(np.sqrt(chi2 / (n * k))) if k > 0 else 0.0,
        "min_expected": float(expected.min()),
        "cells_expected_below_5": int((expected < 5).sum()),
    }


def mean_difference(x: np.ndarray, y: np.ndarray) -> dict:
    """mean(x) - mean(y), with each group's mean, median and size."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    return {
        "mean_x": float(x.mean()), "mean_y": float(y.mean()),
        "median_x": float(np.median(x)), "median_y": float(np.median(y)),
        "diff": float(x.mean() - y.mean()),
        "n_x": len(x), "n_y": len(y),
    }


def describe_rank_biserial(r: float) -> str:
    """Rough size label for |r| (0.1 small, 0.3 medium, 0.5 large)."""
    size = abs(r)
    return ("negligible" if size < 0.1 else "small" if size < 0.3
            else "medium" if size < 0.5 else "large")


def describe_cramers_v(v: float, dof_star: int = 1) -> str:
    """Rough size label for Cramer's V (Cohen), for min(rows, cols) - 1 = dof_star."""
    small, medium, large = (0.1, 0.3, 0.5) if dof_star == 1 else (
        (0.07, 0.21, 0.35) if dof_star == 2 else (0.06, 0.17, 0.29))
    return ("negligible" if v < small else "small" if v < medium
            else "medium" if v < large else "large")


def format_p(p: float) -> str:
    """p-values below what a float can show are reported as an upper bound."""
    if p == 0.0:
        return "< 1e-300"
    return f"{p:.2e}" if p < 0.001 else f"{p:.4f}"
