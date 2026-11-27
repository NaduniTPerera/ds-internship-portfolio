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
import numpy as np  # noqa: E402, F401  (used inside statsmodels formulas: np.log1p)
import pandas as pd  # noqa: E402

from ds_intern.config import PROJECT_ROOT  # noqa: E402
from eda import charts  # noqa: E402  (Day 2 palette and style, reused)
from olist.order_table import load_orders  # noqa: E402
from olist.stats import (  # noqa: E402
    adjust_pvalues,
    bootstrap_mean_diff,
    chi_square,
    describe_cramers_v,
    describe_rank_biserial,
    effect_by_group,
    format_p,
    mann_whitney,
    mean_difference,
    pairwise_proportion_tests,
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
    gap = max(abs(boot["ci_low"] - t["ci_low"]), abs(boot["ci_high"] - t["ci_high"]))
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
        f"- **The two intervals agree** to within {gap:.3f} stars at either end. "
        "Their standard errors match too.",
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


# --------------------------------------------------------------------------- Task 5
def states_results(orders: pd.DataFrame) -> dict:
    from statsmodels.stats.proportion import proportion_confint

    by_state = orders.groupby("customer_state").agg(
        total=("is_late", "size"), events=("is_late", "sum"),
        promised_days=("estimated_delivery_date",
                       lambda s: (s - orders.loc[s.index, "purchase_date"]).dt.days.median()),
        actual_days=("delivery_days", "median"),
        actual_iqr=("delivery_days", lambda s: s.quantile(0.75) - s.quantile(0.25)),
    )
    by_state[["total", "events"]] = by_state[["total", "events"]].astype(int)
    by_state["rate"] = by_state["events"] / by_state["total"]
    low, high = proportion_confint(by_state["events"], by_state["total"], method="wilson")
    by_state["ci_low"], by_state["ci_high"] = low, high
    by_state["margin_days"] = by_state["promised_days"] - by_state["actual_days"]
    by_state = by_state.sort_values("rate")

    table = pd.crosstab(orders["customer_state"], orders["is_late"])
    overall = chi_square(table)

    pairs = pairwise_proportion_tests(by_state[["events", "total"]])
    pairs = pd.concat([pairs, adjust_pvalues(pairs["p_value"].to_numpy())], axis=1)
    corr = by_state[["rate", "margin_days"]].corr(method="spearman").iat[0, 1]
    return {"by_state": by_state, "overall": overall, "pairs": pairs,
            "overall_rate": orders["is_late"].mean(), "margin_rate_spearman": corr}


def plot_states(r: dict) -> plt.Figure:
    charts.apply_style()
    s = r["by_state"]
    fig, ax = plt.subplots(figsize=(10, 8))
    y = range(len(s))
    ax.errorbar(s["rate"] * 100, list(y),
                xerr=[(s["rate"] - s["ci_low"]) * 100, (s["ci_high"] - s["rate"]) * 100],
                fmt="o", color=charts.BLUE, ecolor=charts.BLUE, elinewidth=1.5,
                markersize=6, capsize=0)
    ax.axvline(r["overall_rate"] * 100, color=charts.INK_2, linewidth=1)
    ax.annotate(f"all orders {r['overall_rate'] * 100:.1f}%",
                xy=(r["overall_rate"] * 100, len(s) - 0.5), xytext=(4, 0),
                textcoords="offset points", fontsize=9, color=charts.INK_2)
    ax.set_yticks(list(y), [f"{st} (n={n:,})" for st, n in zip(s.index, s["total"],
                                                                strict=True)])
    ax.set_xlabel("% of orders delivered late (95% Wilson interval)")
    ax.set_title("Late-delivery rate ranges from about 3% to 21% by customer state")
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    return fig


def states_markdown(r: dict) -> str:
    s, o, pairs = r["by_state"], r["overall"], r["pairs"]
    n_pairs = len(pairs)
    sig = {k: int(pairs[k].sum()) for k in ["sig_raw", "sig_bonferroni", "sig_bh"]}
    top = pairs[pairs["sig_bonferroni"]].assign(abs_diff=lambda d: d["diff"].abs())
    top = top.sort_values("abs_diff", ascending=False).head(10)
    tests_used = pairs["test"].value_counts().to_dict()
    lines = [
        "# Day 3 - Task 5: Is lateness different across customer states?",
        "",
        f"Data: all {int(s['total'].sum()):,} delivered orders (a review is not needed for "
        "lateness). Code: `states_results` in `src/olist/analysis.py`.",
        "",
        "## 1. Overall test",
        "",
        "- **H0:** the late rate is the same in all 27 states. "
        "**H1:** at least one state differs. α = 0.05.",
        "- **Test:** chi-square test of independence on the 27 × 2 table (state × late), "
        "because both variables are categorical.",
        f"- **Assumption:** expected counts ≥ 5. {o['cells_expected_below_5']} of 54 cells "
        f"are below 5 (smallest {o['min_expected']:.1f}, the tiny states RR and AP). That is "
        "under the usual 20% limit (Cochran's rule), so the test is valid.",
        "",
        f"**Result:** χ² = {o['chi2']:,.0f}, df = {o['dof']}, p {format_p(o['p_value'])}, "
        f"Cramér's V = {o['cramers_v']:.3f} ({describe_cramers_v(o['cramers_v'])}). "
        "**Reject H0:** lateness depends on the customer's state. The effect size is modest "
        "because most orders come from a few big states with similar rates.",
        "",
        "![Late rate by state](../figures/day3_late_rate_by_state.png)",
        "",
        "## 2. Pairwise tests and multiple comparisons",
        "",
        f"Every pair of states was compared: **{n_pairs} tests** (2×2 chi-square, or "
        "Fisher's exact test when an expected count is below 5. Used: "
        f"{', '.join(f'{k} {v}' for k, v in tests_used.items())}).",
        "",
        f"**Why correct?** At α = 0.05, each test has a 5% false-alarm rate. Even if no "
        f"states differed, about {0.05 * n_pairs:.0f} of {n_pairs} tests would be "
        "'significant' by chance.",
        "",
        "| Method | Rule | Significant pairs |",
        "|---|---|---:|",
        f"| No correction | p < 0.05 | {sig['sig_raw']} |",
        f"| Bonferroni | p < 0.05 / {n_pairs} = {0.05 / n_pairs:.6f} (controls the chance of "
        f"*any* false alarm) | {sig['sig_bonferroni']} |",
        f"| Benjamini-Hochberg | false discovery rate 5% (≈ 5% of the reported pairs may be "
        f"false alarms) | {sig['sig_bh']} |",
        "",
        "Bonferroni is the strictest and safest for a headline claim. BH keeps more real "
        "differences and is the usual choice when exploring many pairs.",
        "",
        "**Largest differences that survive Bonferroni:**",
        "",
        "| State A | Late % | State B | Late % | Difference (pts) | Bonferroni p |",
        "|---|---:|---|---:|---:|---:|",
        *[f"| {p.group_a} | {100 * p.rate_a:.1f} | {p.group_b} | {100 * p.rate_b:.1f} "
          f"| {100 * p.diff:+.1f} | {format_p(p.p_bonferroni)} |" for p in top.itertuples()],
        "",
        "## 3. Late rate by state",
        "",
        "| State | Orders | Late | Late % | 95% CI | Median promised days | "
        "Median actual days | Spread of actual days (IQR) |",
        "|---|---:|---:|---:|---|---:|---:|---:|",
        # itertuples keeps each column's dtype (iterrows would turn the counts into floats)
        *[f"| {row.Index} | {row.total:,} | {row.events:,} | {100 * row.rate:.1f} "
          f"| [{100 * row.ci_low:.1f}, {100 * row.ci_high:.1f}] | {row.promised_days:.0f} "
          f"| {row.actual_days:.0f} | {row.actual_iqr:.0f} |"
          for row in s.sort_values("rate", ascending=False).itertuples()],
        "",
        "## Interpretation",
        "",
        "'Late' is measured against the **promised** date, not against raw delivery speed. "
        "Two things explain the differences between states:",
        "",
        "1. **How generous the estimate is.** Remote northern states (AM, AP, RO, AC) have "
        "some of the *longest* deliveries (median 18-26 days) but the *lowest* late rates, "
        "because they are promised 38-48 days. Across states, a larger median margin "
        f"(promised - actual days) goes with a lower late rate (Spearman ρ = "
        f"{r['margin_rate_spearman']:.2f}).",
        "2. **How predictable delivery is.** The highest late rates (AL, MA, SE, CE, BA, RJ) "
        "are *not* explained by tighter typical margins: their median margin (10-13 days) is "
        "similar to SP, MG and PR (11-14 days), which are late only 4-5% of the time. "
        "Instead, their delivery times are more spread out (IQR 10-15 days vs 6-8 days), so "
        "more orders fall past the promised date.",
        "",
        "- **Small states have wide intervals** (e.g. RR with 41 orders: 12% late, 95% CI "
        "5-26%). Their rates are uncertain, so few of their pairwise tests survive correction.",
        "- **Business implication:** the same fixed buffer would not fix every state. "
        "Unpredictable routes need either a larger buffer or better logistics.",
        "",
    ]
    return "\n".join(lines)


def run_states() -> None:
    results = states_results(load_orders())
    fig = plot_states(results)
    fig.savefig(charts.FIGURE_DIR / "day3_late_rate_by_state.png", bbox_inches="tight")
    plt.close(fig)
    path = REPORT_DIR / "q2_lateness_by_state.md"
    path.write_text(states_markdown(results), encoding="utf-8")
    p = results["pairs"]
    logger.info("States: chi2 p=%s V=%.3f; pairs %d, sig raw %d, bonf %d, BH %d; rho %.2f -> %s",
                format_p(results["overall"]["p_value"]), results["overall"]["cramers_v"],
                len(p), p["sig_raw"].sum(), p["sig_bonferroni"].sum(), p["sig_bh"].sum(),
                results["margin_rate_spearman"], path)


# --------------------------------------------------------------------------- Task 6
MIN_PER_SIDE = 30   # late AND on-time orders needed for a group to be analysed


def simpson_results(orders: pd.DataFrame) -> dict:
    import statsmodels.formula.api as smf

    d = scored_orders(orders)
    crude = mean_difference(d.loc[d["is_late"], "review_score"],
                            d.loc[~d["is_late"], "review_score"])["diff"]
    regions = effect_by_group(d, "customer_region", "is_late", "review_score", MIN_PER_SIDE)
    categories = effect_by_group(d, "category", "is_late", "review_score", MIN_PER_SIDE)

    # composition: does the confounder differ between late and on-time orders?
    region_mix = d.groupby("customer_region").agg(
        orders=("is_late", "size"), late_pct=("is_late", "mean"),
        on_time_score=("review_score", lambda s: s[~d.loc[s.index, "is_late"]].mean()))

    model_data = d.assign(is_late=d["is_late"].astype(int))
    fits = {
        "crude": smf.ols("review_score ~ is_late", model_data).fit(cov_type="HC3"),
        "region": smf.ols("review_score ~ is_late + C(customer_region)",
                          model_data).fit(cov_type="HC3"),
        "region + category": smf.ols("review_score ~ is_late + C(customer_region) "
                                     "+ C(category)", model_data).fit(cov_type="HC3"),
        "region + category + price, freight, items": smf.ols(
            "review_score ~ is_late + C(customer_region) + C(category) + np.log1p(price) "
            "+ np.log1p(freight) + n_items", model_data).fit(cov_type="HC3"),
    }
    coefs = pd.DataFrame([{
        "model": name, "is_late_coef": fit.params["is_late"],
        "ci_low": fit.conf_int().loc["is_late", 0], "ci_high": fit.conf_int().loc["is_late", 1],
        "n": int(fit.nobs)} for name, fit in fits.items()])
    n_categories_total = d["category"].nunique()
    return {"crude": crude, "regions": regions, "categories": categories,
            "region_mix": region_mix, "coefs": coefs,
            "n_categories_total": n_categories_total}


def plot_simpson(r: dict, top_categories: int = 20) -> plt.Figure:
    charts.apply_style()
    regions = r["regions"].sort_values("diff")
    cats = (r["categories"].sort_values("n_flag", ascending=False).head(top_categories)
            .sort_values("diff"))
    fig, axes = plt.subplots(1, 2, figsize=(14, 7.5),
                             gridspec_kw={"width_ratios": [1, 1.4]})
    for ax, data, label, title in [
        (axes[0], regions, "customer_region", "By customer region"),
        (axes[1], cats, "category", f"By category (the {top_categories} with most late orders)"),
    ]:
        y = range(len(data))
        ax.errorbar(data["diff"], list(y),
                    xerr=[data["diff"] - data["ci_low"], data["ci_high"] - data["diff"]],
                    fmt="o", color=charts.BLUE, elinewidth=1.5, markersize=6, capsize=0)
        ax.axvline(0, color=charts.INK_2, linewidth=1, label="No effect (0)")
        ax.axvline(r["crude"], color=charts.ORANGE, linewidth=1.5,
                   label=f"All orders ({r['crude']:.2f})")
        ax.set_yticks(list(y), [f"{g} (late n={n:,})" for g, n in
                                zip(data[label], data["n_flag"], strict=True)])
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("Late - on-time mean score (stars, 95% CI)")
        ax.set_xlim(-3.2, 0.3)
        ax.grid(axis="y", visible=False)
    # the area between -1 and 0 is empty in every row; stop just left of the 0 line
    axes[1].legend(loc="lower right", bbox_to_anchor=(0.89, 0.0))
    low, high = r["categories"]["diff"].max(), r["categories"]["diff"].min()
    fig.suptitle(f"Inside every region and every large category, late orders score "
                 f"{abs(low):.1f}-{abs(high):.1f} stars lower: no Simpson's paradox",
                 x=0.01, ha="left", fontsize=13, fontweight="bold", color=charts.INK)
    fig.tight_layout()
    return fig


def simpson_markdown(r: dict) -> str:
    regions, cats, coefs, mix = r["regions"], r["categories"], r["coefs"], r["region_mix"]
    n_cat = len(cats)
    neg = int((cats["diff"] < 0).sum())
    ci_below_zero = int((cats["ci_high"] < 0).sum())
    adjusted = coefs.iloc[-1]
    lines = [
        "# Day 3 - Task 6: Simpson's paradox check (does the effect hold inside groups?)",
        "",
        "Code: `simpson_results` in `src/olist/analysis.py`, `effect_by_group` in "
        "`src/olist/stats.py`.",
        "",
        "## Confounding in plain words",
        "",
        "A **confounder** is a third factor that affects *both* things we compare. Region is "
        "a candidate: some regions have many more late orders (Task 5), and customers in "
        "different regions might also rate differently for other reasons (expectations, "
        "product mix, sellers). If so, part of 'late orders score lower' could really be "
        "'orders from that region score lower', with lateness just tagging along. "
        "Product category is a similar candidate: bulky items (furniture) are late more "
        "often *and* might disappoint more anyway.",
        "",
        "**Simpson's paradox** is the extreme case: a trend in the pooled data disappears or "
        "*reverses* inside every group, because the groups are mixed in different "
        "proportions. Classic example: a hospital with a higher overall death rate can be "
        "better for both mild and severe patients, if it treats far more severe cases.",
        "",
        "**Check:** compute the late-vs-on-time difference *inside* each region and each "
        "product category, then adjust for all of them at once with a regression.",
        "",
        f"## 1. Inside each region (pooled difference: {r['crude']:.2f} stars)",
        "",
        "| Region | Late orders | On-time orders | Late % | Mean late | Mean on time "
        "| Difference [95% CI] | Rank-biserial r |",
        "|---|---:|---:|---:|---:|---:|---|---:|",
        *[f"| {g.customer_region} | {g.n_flag:,} | {g.n_other:,} "
          f"| {100 * mix.loc[g.customer_region, 'late_pct']:.1f} | {g.mean_flag:.2f} "
          f"| {g.mean_other:.2f} | {g.diff:.2f} [{g.ci_low:.2f}, {g.ci_high:.2f}] "
          f"| {g.rank_biserial:.2f} |" for g in regions.sort_values("diff").itertuples()],
        "",
        "Region **is** linked to lateness (the late rate varies a lot), and the on-time "
        "baseline score varies a little between regions. So it is a plausible confounder. "
        "But **in every region, late orders score far lower**, and every confidence interval "
        "is well below 0.",
        "",
        "## 2. Inside each product category",
        "",
        f"{n_cat} of {r['n_categories_total']} categories have at least {MIN_PER_SIDE} late "
        f"and {MIN_PER_SIDE} on-time reviewed orders (smaller ones are too noisy to test "
        "alone, but they are included in the regression below).",
        "",
        f"- Late orders score lower in **{neg} of {n_cat}** categories.",
        f"- The 95% CI is entirely below 0 in **{ci_below_zero} of {n_cat}**.",
        f"- The difference ranges from {cats['diff'].min():.2f} "
        f"({cats.loc[cats['diff'].idxmin(), 'category']}) to {cats['diff'].max():.2f} "
        f"({cats.loc[cats['diff'].idxmax(), 'category']}) stars.",
        "",
        "![Effect inside groups](../figures/day3_simpson_check.png)",
        "",
        "## 3. Adjusting for everything at once (linear regression)",
        "",
        "`review_score ~ is_late + controls` with robust (HC3) standard errors. The "
        "`is_late` coefficient is the late-vs-on-time difference *after* holding the "
        "controls fixed. Treating the 1-5 score as numeric is a simplification, used here "
        "only to compare the raw and adjusted effect.",
        "",
        "| Controls | is_late effect (stars) | 95% CI | Orders |",
        "|---|---:|---|---:|",
        *[f"| {c.model} | {c.is_late_coef:.3f} | [{c.ci_low:.3f}, {c.ci_high:.3f}] "
          f"| {c.n:,} |" for c in coefs.itertuples()],
        "",
        f"Adding region, category, price, freight and number of items moves the effect from "
        f"{coefs.iloc[0]['is_late_coef']:.2f} to {adjusted['is_late_coef']:.2f} stars, a "
        f"change of {abs(adjusted['is_late_coef'] - coefs.iloc[0]['is_late_coef']):.2f}. "
        "These variables are **not** what explains the effect.",
        "",
        "## Conclusion",
        "",
        "- **No Simpson's paradox:** the effect has the same direction and a similar size "
        "inside every region and every large category, and it survives adjustment.",
        "- **Confounding by region, category, price or order size is small.**",
        "- **Still not proof of causation.** We can only adjust for variables we *have*. An "
        "unmeasured factor, for example an unreliable seller who is *both* slow and sends "
        "poor-quality products, could still explain part of the gap. A randomised experiment "
        "(Task 7) is the way to measure the causal effect of delivery promises.",
        "",
    ]
    return "\n".join(lines)


def run_simpson() -> None:
    results = simpson_results(load_orders())
    fig = plot_simpson(results)
    fig.savefig(charts.FIGURE_DIR / "day3_simpson_check.png", bbox_inches="tight")
    plt.close(fig)
    path = REPORT_DIR / "q3_simpson_check.md"
    path.write_text(simpson_markdown(results), encoding="utf-8")
    cats = results["categories"]
    logger.info("Simpson: crude %.2f; regions %s; categories %d (neg %d, max %.2f); "
                "adjusted %.3f -> %s", results["crude"],
                results["regions"]["diff"].round(2).tolist(), len(cats),
                int((cats["diff"] < 0).sum()), cats["diff"].max(),
                results["coefs"].iloc[-1]["is_late_coef"], path)


QUESTIONS = {"q1": run_q1, "bootstrap": run_bootstrap, "states": run_states,
             "simpson": run_simpson}


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
