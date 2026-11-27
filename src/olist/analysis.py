"""Day 3 analyses on the order-level table. One function per question.

Usage:
    uv run python -m olist.analysis q1     # Task 3: late vs on-time review scores
"""

import argparse
import logging
import sys
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from ds_intern.config import PROJECT_ROOT  # noqa: E402
from eda import charts  # noqa: E402  (Day 2 palette and style, reused)
from olist.order_table import load_orders  # noqa: E402
from olist.stats import (  # noqa: E402
    bootstrap_mean_diff,
    chi_square,
    describe_cramers_v,
    describe_rank_biserial,
    format_p,
    mann_whitney,
    mean_difference,
    welch_t_interval,
)

logger = logging.getLogger(__name__)

REPORT_DIR = PROJECT_ROOT / "reports" / "day3"
ALPHA = 0.05
SCORES = [1, 2, 3, 4, 5]


def scored_orders(orders: pd.DataFrame) -> pd.DataFrame:
    """Orders that have a review score (the population for the score tests)."""
    return orders[orders["review_score"].notna()].assign(
        review_score=lambda d: d["review_score"].astype(int))


def first_order_per_customer(orders: pd.DataFrame) -> pd.DataFrame:
    """Keep each customer's first order, so every row is an independent person."""
    return orders.sort_values("purchase_ts").drop_duplicates("customer_unique_id")


# --------------------------------------------------------------------------- Q1
def q1_results(orders: pd.DataFrame) -> dict:
    d = scored_orders(orders)
    late = d.loc[d["is_late"], "review_score"].to_numpy()
    on_time = d.loc[~d["is_late"], "review_score"].to_numpy()

    table = pd.crosstab(d["is_late"].map({False: "on time", True: "late"}),
                        d["review_score"]).reindex(columns=SCORES, fill_value=0)

    independent = scored_orders(first_order_per_customer(orders))
    return {
        "means": mean_difference(late, on_time),
        "mann_whitney": mann_whitney(late, on_time),
        "chi_square": chi_square(table),
        "table": table,
        "pct": table.div(table.sum(axis=1), axis=0) * 100,
        "independent_mw": mann_whitney(
            independent.loc[independent["is_late"], "review_score"],
            independent.loc[~independent["is_late"], "review_score"]),
        "n_independent": len(independent),
    }


def plot_q1(pct: pd.DataFrame) -> plt.Figure:
    charts.apply_style()
    fig, ax = plt.subplots(figsize=(10, 5))
    width = 0.38
    x = range(len(SCORES))
    for offset, group, color in [(-width / 2, "on time", charts.BLUE),
                                 (width / 2, "late", charts.ORANGE)]:
        values = pct.loc[group, SCORES]
        bars = ax.bar([i + offset for i in x], values, width=width - 0.02, color=color,
                      label={"on time": "On-time orders", "late": "Late orders"}[group])
        for bar, v in zip(bars, values, strict=True):
            if v >= 15:   # label only the big bars; the rest are readable from the axis
                ax.annotate(f"{v:.0f}%", xy=(bar.get_x() + bar.get_width() / 2, v),
                            xytext=(0, 3), textcoords="offset points", ha="center",
                            fontsize=9, color=charts.INK)
    ax.set_xticks(list(x), [f"{s} star{'s' if s > 1 else ''}" for s in SCORES])
    ax.set_ylabel("% of orders in the group")
    ax.set_title("Late orders are mostly 1-star; on-time orders are mostly 5-star")
    ax.legend(loc="upper center")
    ax.grid(axis="x", visible=False)
    fig.tight_layout()
    return fig


def q1_markdown(r: dict) -> str:
    m, mw, cs, ind = r["means"], r["mann_whitney"], r["chi_square"], r["independent_mw"]
    pct = r["pct"]
    reject = mw["p_value"] < ALPHA and cs["p_value"] < ALPHA
    lines = [
        "# Day 3 - Question 1: Do late orders get lower review scores?",
        "",
        "Data: delivered orders with a review score "
        f"({m['n_x'] + m['n_y']:,} orders: {m['n_x']:,} late, {m['n_y']:,} on time). "
        "Code: `src/olist/analysis.py`, `src/olist/stats.py`.",
        "",
        "## Hypotheses (α = 0.05, two-sided)",
        "",
        "- **H0:** review scores have the same distribution for late and on-time orders.",
        "- **H1:** the distributions differ.",
        "",
        "## Choice of tests",
        "",
        "- **Mann-Whitney U (main test).** `review_score` is ordinal (1-5 stars): the order "
        "matters, but the steps are not guaranteed to be equal, and the scores are far from "
        "normal (most are 5). Mann-Whitney compares ranks and does not assume normality or "
        "equal spacing. A t-test would.",
        "- **Chi-square test of independence (second test).** It compares the whole score "
        "distribution (counts of 1, 2, 3, 4, 5 stars) between the two groups.",
        "- **Assumptions:** observations should be independent. Some customers ordered more "
        "than once, so the test is repeated with one order per customer (below). Chi-square "
        f"needs expected counts ≥ 5: the smallest expected count is {cs['min_expected']:,.0f}, "
        f"and {cs['cells_expected_below_5']} cells are below 5.",
        "",
        "## Score distribution (% of orders in each group)",
        "",
        "| Group | 1★ | 2★ | 3★ | 4★ | 5★ | Mean | Median |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        f"| On time | {' | '.join(f'{v:.1f}' for v in pct.loc['on time', SCORES])} "
        f"| {m['mean_y']:.2f} | {m['median_y']:.0f} |",
        f"| Late | {' | '.join(f'{v:.1f}' for v in pct.loc['late', SCORES])} "
        f"| {m['mean_x']:.2f} | {m['median_x']:.0f} |",
        "",
        "![Score distribution](../figures/day3_q1_score_distribution.png)",
        "",
        "## Results",
        "",
        "| Test | Statistic | p-value | Effect size | Size |",
        "|---|---:|---:|---:|---|",
        f"| Mann-Whitney U | U = {mw['U']:,.0f} | {format_p(mw['p_value'])} "
        f"| rank-biserial r = {mw['rank_biserial']:.3f} "
        f"| {describe_rank_biserial(mw['rank_biserial'])} |",
        f"| Chi-square (dof = {cs['dof']}) | χ² = {cs['chi2']:,.0f} "
        f"| {format_p(cs['p_value'])} | Cramér's V = {cs['cramers_v']:.3f} "
        f"| {describe_cramers_v(cs['cramers_v'])} |",
        f"| Difference in means (late - on time) | | | {m['diff']:+.2f} stars | |",
        "",
        f"- **Common-language effect size:** a random late order scores higher than a random "
        f"on-time order with probability {mw['cles']:.2f} (ties count as half). With no "
        "effect, this would be 0.50.",
        f"- **Robustness:** with one order per customer ({r['n_independent']:,} orders), "
        f"rank-biserial r = {ind['rank_biserial']:.3f}, p {format_p(ind['p_value'])}. "
        "The result does not depend on repeat customers.",
        "",
        "## Conclusion",
        "",
        f"{'**Reject H0.**' if reject else '**Do not reject H0.**'} Late orders get much lower "
        f"review scores: on average {abs(m['diff']):.2f} stars lower ({m['mean_x']:.2f} vs "
        f"{m['mean_y']:.2f}), and the median drops from {m['median_y']:.0f} stars to "
        f"{m['median_x']:.0f} star{'s' if m['median_x'] != 1 else ''}. "
        f"{pct.loc['late', 1]:.0f}% of late orders get 1 star, "
        f"compared with {pct.loc['on time', 1]:.0f}% of on-time orders. The effect is "
        f"**{describe_rank_biserial(mw['rank_biserial'])}** (r = {mw['rank_biserial']:.2f}), "
        "not just statistically significant. With about 95,000 orders, even tiny differences "
        "would be significant, which is why the effect size matters.",
        "",
        "**Caution:** this is an association in observational data, not yet proof that "
        "lateness *causes* low scores. Late orders may differ in other ways (region, "
        "category, price). Task 6 (Simpson's paradox check) looks at this.",
        "",
    ]
    return "\n".join(lines)


def run_q1() -> None:
    results = q1_results(load_orders())
    fig = plot_q1(results["pct"])
    charts.FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(charts.FIGURE_DIR / "day3_q1_score_distribution.png", bbox_inches="tight")
    plt.close(fig)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / "q1_late_vs_reviews.md"
    path.write_text(q1_markdown(results), encoding="utf-8")
    mw = results["mann_whitney"]
    logger.info("Q1: diff %.2f stars, U p=%s, r=%.3f, V=%.3f -> %s",
                results["means"]["diff"], format_p(mw["p_value"]), mw["rank_biserial"],
                results["chi_square"]["cramers_v"], path)


# --------------------------------------------------------------------------- Task 4
def bootstrap_results(orders: pd.DataFrame, n_resamples: int = 10_000) -> dict:
    d = scored_orders(orders)
    late = d.loc[d["is_late"], "review_score"].to_numpy()
    on_time = d.loc[~d["is_late"], "review_score"].to_numpy()
    started = time.perf_counter()
    boot = bootstrap_mean_diff(late, on_time, n_resamples=n_resamples, seed=42)
    boot["seconds"] = time.perf_counter() - started
    return {"bootstrap": boot, "t": welch_t_interval(late, on_time),
            "n_late": len(late), "n_on_time": len(on_time)}


def plot_bootstrap(r: dict) -> plt.Figure:
    charts.apply_style()
    boot, t = r["bootstrap"], r["t"]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(boot["diffs"], bins=60, color=charts.BLUE, edgecolor="white", linewidth=0.4)
    ax.axvspan(boot["ci_low"], boot["ci_high"], color=charts.BLUE, alpha=0.12,
               label=f"Bootstrap 95% CI [{boot['ci_low']:.3f}, {boot['ci_high']:.3f}]")
    for v in (t["ci_low"], t["ci_high"]):
        ax.axvline(v, color=charts.ORANGE, linewidth=2)
    ax.plot([], [], color=charts.ORANGE, linewidth=2,
            label=f"Welch t-interval [{t['ci_low']:.3f}, {t['ci_high']:.3f}]")
    ax.axvline(boot["estimate"], color=charts.INK, linewidth=1)
    ax.annotate(f"observed {boot['estimate']:.3f}", xy=(boot["estimate"], ax.get_ylim()[1]),
                xytext=(4, -12), textcoords="offset points", fontsize=9, color=charts.INK)
    ax.set_title("10,000 bootstrap resamples: the difference is about -2 stars, "
                 "and both intervals agree")
    ax.set_xlabel("Difference in mean review score (late - on time), stars")
    ax.set_ylabel("Number of resamples")
    ax.legend(loc="upper left")
    fig.tight_layout()
    return fig


def bootstrap_markdown(r: dict) -> str:
    boot, t = r["bootstrap"], r["t"]
    width_b = boot["ci_high"] - boot["ci_low"]
    width_t = t["ci_high"] - t["ci_low"]
    return "\n".join([
        "# Day 3 - Task 4: Bootstrap 95% CI for the difference in mean review score",
        "",
        f"Difference = mean score of late orders - mean score of on-time orders "
        f"({r['n_late']:,} late, {r['n_on_time']:,} on time). "
        "Code: `bootstrap_mean_diff` and `welch_t_interval` in `src/olist/stats.py`.",
        "",
        "## Method",
        "",
        "**Bootstrap (written with NumPy):**",
        "",
        "1. Resample the late orders *with replacement* (same size as the group), and do "
        "the same for the on-time orders.",
        "2. Compute mean(late) - mean(on time) and store it.",
        f"3. Repeat {boot['n_resamples']:,} times (seed 42, in batches of 200 to limit memory).",
        "4. The 2.5th and 97.5th percentiles of the stored differences form the 95% CI "
        "(percentile method).",
        "",
        "**Analytical:** Welch's t-interval, diff ± t × SE, with "
        "SE = √(s²_late/n_late + s²_on-time/n_on-time) and Welch-Satterthwaite degrees of "
        f"freedom (df = {t['dof']:,.0f}). Welch's version is used because the variances "
        "differ: late scores are spread across 1-5, on-time scores sit mostly at 5.",
        "",
        "## Results",
        "",
        "| Method | Estimate | 95% CI | Width | Standard error |",
        "|---|---:|---|---:|---:|",
        f"| Bootstrap (percentile, {boot['n_resamples']:,} resamples) | {boot['estimate']:.4f} "
        f"| [{boot['ci_low']:.4f}, {boot['ci_high']:.4f}] | {width_b:.4f} "
        f"| {boot['std_error']:.4f} |",
        f"| Welch t-interval | {t['estimate']:.4f} | [{t['ci_low']:.4f}, {t['ci_high']:.4f}] "
        f"| {width_t:.4f} | {t['std_error']:.4f} |",
        "",
        "![Bootstrap distribution](../figures/day3_bootstrap_ci.png)",
        "",
        "## Comparison",
        "",
        f"- **The two intervals agree** to within {max(abs(boot['ci_low'] - t['ci_low']), abs(boot['ci_high'] - t['ci_high'])):.3f} "
        "stars at either end. Their standard errors match too.",
        "- **Why they agree:** review scores are far from normal, but the t-interval is about "
        "the *mean*. With thousands of orders per group, the Central Limit Theorem makes the "
        "sample mean almost normal (the bootstrap histogram is bell-shaped). The bootstrap "
        "makes no normality assumption, so its agreement confirms the t-interval is valid here.",
        "- **When they would differ:** with small groups, very skewed data, or a statistic with "
        "no simple formula (for example the median or a ratio). There, the bootstrap is the "
        "safer choice.",
        f"- **Conclusion:** we are 95% confident that late orders score between "
        f"{abs(boot['ci_high']):.2f} and {abs(boot['ci_low']):.2f} stars lower on average "
        "than on-time orders. The interval is far from 0, which matches the tests in Task 3.",
        f"- Runtime: {boot['n_resamples']:,} resamples took {boot['seconds']:.1f} s.",
        "",
    ])


def run_bootstrap() -> None:
    results = bootstrap_results(load_orders())
    fig = plot_bootstrap(results)
    fig.savefig(charts.FIGURE_DIR / "day3_bootstrap_ci.png", bbox_inches="tight")
    plt.close(fig)
    path = REPORT_DIR / "q1_bootstrap_ci.md"
    path.write_text(bootstrap_markdown(results), encoding="utf-8")
    b, t = results["bootstrap"], results["t"]
    logger.info("Bootstrap [%.4f, %.4f] vs Welch [%.4f, %.4f] in %.1f s -> %s",
                b["ci_low"], b["ci_high"], t["ci_low"], t["ci_high"], b["seconds"], path)


QUESTIONS = {"q1": run_q1, "bootstrap": run_bootstrap}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a Day 3 analysis.")
    parser.add_argument("question", choices=sorted(QUESTIONS))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    QUESTIONS[args.question]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
