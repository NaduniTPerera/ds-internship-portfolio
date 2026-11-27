"""Day 3 analyses on the order-level table. One function per question.

Usage:
    uv run python -m olist.analysis q1     # Task 3: late vs on-time review scores
"""

import argparse
import logging
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from ds_intern.config import PROJECT_ROOT  # noqa: E402
from eda import charts  # noqa: E402  (Day 2 palette and style, reused)
from olist.order_table import load_orders  # noqa: E402
from olist.stats import (  # noqa: E402
    chi_square,
    describe_cramers_v,
    describe_rank_biserial,
    format_p,
    mann_whitney,
    mean_difference,
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


QUESTIONS = {"q1": run_q1}


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
