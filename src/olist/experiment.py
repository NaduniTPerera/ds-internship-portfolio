"""Day 3 Task 7: power analysis and experiment plan for a '+3 days delivery buffer'.

Usage:
    uv run python -m olist.experiment      # writes reports/day3/q4_experiment_plan.md
"""

import argparse
import logging
import math
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402
from statsmodels.stats.power import TTestIndPower  # noqa: E402

from ds_intern.config import PROJECT_ROOT  # noqa: E402
from eda import charts  # noqa: E402
from olist.order_table import load_orders  # noqa: E402

logger = logging.getLogger(__name__)

REPORT_PATH = PROJECT_ROOT / "reports" / "day3" / "q4_experiment_plan.md"
FIGURE_NAME = "day3_power_curve.png"
ALPHA, POWER, MDE = 0.05, 0.80, 0.10
BUFFER_DAYS = 3


def n_per_group(mde: float, sd: float, alpha: float = ALPHA, power: float = POWER) -> int:
    """Orders per group (with a review score) to detect a change of `mde` stars.

    Two-sided two-sample t-test, equal group sizes, via statsmodels.
    Cohen's d = mde / sd.
    """
    n = TTestIndPower().solve_power(effect_size=mde / sd, alpha=alpha, power=power,
                                    ratio=1.0, alternative="two-sided")
    return math.ceil(n)


def n_per_group_formula(mde: float, sd: float, alpha: float = ALPHA,
                        power: float = POWER) -> float:
    """Normal-approximation check: n = 2 (z_{1-a/2} + z_{power})^2 sd^2 / mde^2."""
    z = stats.norm.ppf(1 - alpha / 2) + stats.norm.ppf(power)
    return 2 * z ** 2 * sd ** 2 / mde ** 2


def weeks_needed(n_scored_per_group: int, orders_per_week: float,
                 scored_share: float) -> int:
    """Whole weeks of enrolment for both groups (minimum 2 full weekly cycles)."""
    enrolled_total = 2 * n_scored_per_group / scored_share
    return max(2, math.ceil(enrolled_total / orders_per_week))


def inputs_from_data(orders: pd.DataFrame) -> dict:
    """Everything the plan needs, measured from the historical orders."""
    scored = orders.dropna(subset=["review_score"]).assign(
        score=lambda d: d["review_score"].astype(float))
    recent = orders[(orders["purchase_date"] >= "2018-01-01")
                    & (orders["purchase_date"] < "2018-08-01")]
    weeks = (recent["purchase_date"].max() - recent["purchase_date"].min()).days / 7

    late_1_to_3 = scored["is_late"] & (scored["days_late"] <= BUFFER_DAYS)
    near_on_time = ~scored["is_late"] & (scored["days_late"] >= -BUFFER_DAYS)
    flip_share = (orders["is_late"] & (orders["days_late"] <= BUFFER_DAYS)).mean()
    flip_gain = scored.loc[near_on_time, "score"].mean() - scored.loc[late_1_to_3, "score"].mean()

    by_days_late = scored.groupby(scored["days_late"].clip(-30, 30))["score"].mean()
    now = scored["days_late"].clip(-30, 30).map(by_days_late).mean()
    shifted = (scored["days_late"] - BUFFER_DAYS).clip(-30, 30).map(by_days_late).mean()
    return {
        "n_scored": len(scored),
        "sd": scored["score"].std(),
        "mean_score": scored["score"].mean(),
        "orders_per_week": len(recent) / weeks,
        "scored_share": orders["review_score"].notna().mean(),
        "late_now": orders["is_late"].mean(),
        "late_with_buffer": (orders["days_late"] > BUFFER_DAYS).mean(),
        "flip_share": flip_share,
        "flip_gain": flip_gain,
        "effect_flips_only": flip_share * flip_gain,
        "effect_all_orders": shifted - now,
        "delivery_p95": orders["delivery_days"].quantile(0.95),
        "orders_per_customer": len(orders) / orders["customer_unique_id"].nunique(),
        "by_days_late": by_days_late,
    }


def plot_power_curve(sd: float, inputs: dict) -> plt.Figure:
    charts.apply_style()
    mdes = np.linspace(0.015, 0.2, 200)
    ns = [n_per_group(m, sd) for m in mdes]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.plot(mdes, ns, color=charts.BLUE, linewidth=2)
    ax.set_yscale("log")
    low, high = inputs["effect_flips_only"], inputs["effect_all_orders"]
    ax.axvspan(low, high, color=charts.ORANGE, alpha=0.15)
    ax.annotate(f"realistic effect\n{low:.3f}-{high:.3f} stars", xy=((low + high) / 2, 1_500),
                ha="center", fontsize=9, color=charts.INK)
    n_mde = n_per_group(MDE, sd)
    ax.plot([MDE], [n_mde], "o", color=charts.INK, markersize=7)
    ax.annotate(f"target 0.1 stars:\n{n_mde:,} orders per group", xy=(MDE, n_mde),
                xytext=(12, 10), textcoords="offset points", fontsize=9, color=charts.INK)
    ax.set_xlabel("Minimum detectable change in mean review score (stars)")
    ax.set_ylabel("Reviewed orders needed per group (log scale)")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_title("Halving the detectable effect needs 4x the orders "
                 "(80% power, α = 0.05, two-sided)")
    fig.tight_layout()
    return fig


def plan_markdown(inp: dict) -> str:
    sd = inp["sd"]
    n_target = n_per_group(MDE, sd)
    weeks_target = weeks_needed(n_target, inp["orders_per_week"], inp["scored_share"])
    follow_up_weeks = math.ceil((inp["delivery_p95"] + 7) / 7)   # delivery + ~1 week to review
    rows = []
    for mde in [0.20, 0.10, 0.05, 0.03, 0.02]:
        n = n_per_group(mde, sd)
        rows.append(f"| {mde:.2f} | {mde / sd:.3f} | {n:,} | {2 * n:,} "
                    f"| {weeks_needed(n, inp['orders_per_week'], inp['scored_share'])} |")
    by_dl = inp["by_days_late"]
    return "\n".join([
        "# Day 3 - Task 7: Experiment design for a '+3 days delivery buffer'",
        "",
        "**Feature:** show customers a delivery estimate 3 days later than today. Logistics "
        "do not change; only the promise does. Orders that arrive 1-3 days after today's "
        "estimate would then count as on time.",
        "",
        "**Why an experiment:** Tasks 3-6 found a strong *association* between lateness and "
        "low scores. Random assignment makes the two groups alike in everything "
        "(region, seller, product, and factors we cannot measure), so a difference between "
        "them is *caused* by the feature.",
        "",
        "## 1. Power analysis (statsmodels `TTestIndPower`)",
        "",
        f"- Effect to detect: **{MDE} stars** change in mean review score; α = {ALPHA} "
        f"(two-sided); power = {POWER:.0%}.",
        f"- Noise: standard deviation of review scores = **{sd:.3f}** (measured on "
        f"{inp['n_scored']:,} reviewed orders), so Cohen's d = "
        f"{MDE} / {sd:.3f} = **{MDE / sd:.3f}**.",
        f"- **Result: {n_target:,} reviewed orders per group** ({2 * n_target:,} in total). "
        f"Normal-approximation check: {n_per_group_formula(MDE, sd):,.0f} per group.",
        f"- {inp['scored_share']:.1%} of delivered orders get a review, so about "
        f"{math.ceil(2 * n_target / inp['scored_share']):,} orders must be enrolled.",
        "",
        "| Detectable change (stars) | Cohen's d | Reviewed orders per group | Total "
        "| Weeks of enrolment* |",
        "|---:|---:|---:|---:|---:|",
        *rows,
        "",
        f"*At {inp['orders_per_week']:,.0f} delivered orders per week (Jan-Jul 2018 average), "
        "minimum 2 weeks.",
        "",
        f"![Power curve](../figures/{FIGURE_NAME})",
        "",
        "## 2. Is 0.1 stars a realistic target? (estimated from historical data)",
        "",
        f"- With a +3 day buffer, the late rate would fall from {inp['late_now']:.1%} to "
        f"{inp['late_with_buffer']:.1%}. Only **{inp['flip_share']:.1%} of orders flip** "
        "from late to on time.",
        f"- Orders that are 1-3 days late score {inp['flip_gain']:.2f} stars lower than "
        f"orders delivered just before the estimate. Gain if only flipped orders improve: "
        f"{inp['flip_share']:.4f} × {inp['flip_gain']:.2f} ≈ "
        f"**{inp['effect_flips_only']:.3f} stars**.",
        "- Customers also score orders higher when they arrive *well before* the promise "
        f"(mean score {by_dl.loc[-10]:.2f} at 10 days early vs {by_dl.loc[0]:.2f} on the "
        f"estimated day). If every order gained 3 days of 'earliness', the gain would be about "
        f"**{inp['effect_all_orders']:.3f} stars**.",
        "",
        f"**So the realistic effect is about {inp['effect_flips_only']:.3f}-"
        f"{inp['effect_all_orders']:.3f} stars, below the 0.1 target.** An experiment sized "
        "for 0.1 stars would probably report 'no significant effect' even if the feature "
        "works. These estimates are observational, so they are a guide, not a guarantee.",
        "",
        "**Recommendation:** size the experiment for **0.05 stars** "
        f"({n_per_group(0.05, sd):,} reviewed orders per group, about "
        f"{weeks_needed(n_per_group(0.05, sd), inp['orders_per_week'], inp['scored_share'])}"
        " weeks), or target the buffer at routes where many orders are slightly late "
        "(Northeast states and RJ, Task 5), where the effect per order is larger.",
        "",
        "## 3. Experiment plan",
        "",
        "| Item | Decision | Why |",
        "|---|---|---|",
        "| **Hypotheses** | H0: mean review score is the same in both groups. H1: it differs "
        "(two-sided). | A two-sided test also catches harm, e.g. customers disliking longer "
        "promises. |",
        "| **Unit of randomisation** | **Customer** (`customer_unique_id`), assigned 50/50 by "
        "a hash of the id. | One person always sees the same kind of promise. Randomising "
        "by order would show the same customer different promises (inconsistent, "
        f"contaminated). Customers place {inp['orders_per_customer']:.2f} orders on average, so "
        "clustering barely affects the sample size. |",
        "| **Population** | All customers checking out, all states. | Results apply to the "
        "whole business; region balance is checked after assignment. |",
        "| **Control / treatment** | Control: current estimate. Treatment: estimate + 3 days "
        "everywhere it is shown (checkout, emails, tracking). Sellers and carriers keep "
        "the *original* internal deadline. | Only the promise may differ; if sellers saw "
        "the extra 3 days they might ship slower and the test would measure that instead. |",
        "| **Primary metric** | Mean review score per delivered order. | The business "
        "question is about satisfaction; the MDE is defined on it. |",
        "| **Secondary metrics** | % 1-star reviews; late rate vs the *shown* promise; "
        "review response rate. | Explain *how* the score changes; the late rate should fall "
        "by about 2 percentage points if the feature works as intended. |",
        "| **Guardrail metrics** | Checkout conversion rate; revenue per visitor; "
        "cancellation rate; actual delivery days; 'where is my order' contacts; repeat "
        "purchase within 90 days. | A later promise may **lose sales** (conversion) even if "
        "reviews improve. Actual delivery time must not get slower. |",
        f"| **Sample size** | {n_target:,} reviewed orders per group for 0.1 stars "
        f"(recommended: {n_per_group(0.05, sd):,} for 0.05 stars). | Section 1. |",
        f"| **Duration** | Enrolment: {weeks_target} weeks for the 0.1-star design (always "
        f"whole weeks, minimum 2). Then about {follow_up_weeks} more weeks of follow-up so "
        f"the last orders are delivered (95% within {inp['delivery_p95']:.0f} days) and "
        "reviewed. Avoid Black Friday / Christmas peaks. | Whole weeks cover weekday "
        "patterns; reviews only arrive after delivery. |",
        "| **Stopping rule** | Fixed horizon: analyse the primary metric **once**, when the "
        "planned sample is reached. No peeking. Stop early **only** for harm: a guardrail "
        "breach (e.g. conversion down more than 2% relative at p < 0.001) or a sample ratio "
        "mismatch (chi-square on group sizes, p < 0.001). | Looking at the result repeatedly "
        "and stopping when p < 0.05 inflates false positives far above 5%. |",
        "| **Analysis** | Welch t-test and 95% CI for the difference in mean score "
        "(standard errors clustered by customer); Mann-Whitney U as a robustness check; "
        "guardrails with the same method. | Matches Tasks 3-4. The plan is written *before* "
        "the data arrives. |",
        "| **Decision** | Ship if the primary CI is above 0 **and** no guardrail is harmed. "
        "| A better review score is not worth losing sales. |",
        "",
    ])


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description="Power analysis + experiment plan.").parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    inputs = inputs_from_data(load_orders())
    fig = plot_power_curve(inputs["sd"], inputs)
    fig.savefig(charts.FIGURE_DIR / FIGURE_NAME, bbox_inches="tight")
    plt.close(fig)
    REPORT_PATH.write_text(plan_markdown(inputs), encoding="utf-8")
    logger.info("SD %.3f -> n per group for %.2f stars: %d; realistic effect %.3f-%.3f -> %s",
                inputs["sd"], MDE, n_per_group(MDE, inputs["sd"]),
                inputs["effect_flips_only"], inputs["effect_all_orders"], REPORT_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
