"""EDA charts for the cleaned NYC taxi data (Jan-Jun 2024).

Memory-friendly by design (the laptop has ~8 GB RAM):
- Aggregates (counts, trends, heatmap) run in DuckDB over all cleaned rows,
  so pandas only receives small results.
- Row-level charts (distributions, scatter, box plots, correlation) use a
  reproducible random sample.

Each plot_* function returns a matplotlib Figure. save() writes it to
reports/figures/. Used by notebooks/day2_eda.ipynb.

Colors: one validated palette. A single series uses one blue. Heatmaps use one
blue hue (light to dark). Correlation uses blue <-> red with a gray midpoint.
No chart has two y-axes.
"""

from pathlib import Path

import duckdb
import matplotlib
import matplotlib.dates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

from ds_intern.config import PROCESSED_DATA_DIR, PROJECT_ROOT, RAW_DATA_DIR

FIGURE_DIR = PROJECT_ROOT / "reports" / "figures"
SAMPLE_ROWS = 300_000
SEED = 42

# Palette (validated categorical slots + chart ink)
BLUE = "#257de0"        # series 1
ORANGE = "#f47230"      # series 2 (reference line)
GRAY = "#9c9c9c"        # de-emphasised (raw data)
INK = "#191919"
INK_2 = "#666666"
GRID = "#e7e7e7"
AXIS = "#c2c2c2"
BLUE_RAMP = ["#cce3fd", "#9dc8f7", "#6aabf1", "#338ced", "#2370cd", "#1757ac", "#0e3d7e"]
SEQUENTIAL = LinearSegmentedColormap.from_list("blue_seq", BLUE_RAMP)
DIVERGING = LinearSegmentedColormap.from_list(
    "blue_gray_red", ["#1757ac", "#84b9f3", "#efefef", "#f08a8b", "#c0292a"])

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
PAYMENT_NAMES = {0: "Flex Fare", 1: "Credit card", 2: "Cash", 3: "No charge", 4: "Dispute",
                 5: "Unknown", 6: "Voided"}


# --------------------------------------------------------------------------- setup
def apply_style() -> None:
    plt.rcParams.update({
        "figure.dpi": 110,
        "savefig.dpi": 140,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": AXIS,
        "axes.labelcolor": INK_2,
        "axes.titlecolor": INK,
        "axes.titlesize": 13,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.labelsize": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "xtick.color": INK_2,
        "ytick.color": INK_2,
        "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"],
        "legend.frameon": False,
    })


def connect(processed_dir: Path = PROCESSED_DATA_DIR,
            raw_dir: Path = RAW_DATA_DIR) -> duckdb.DuckDBPyConnection:
    """DuckDB connection with views: clean, raw, zones."""
    con = duckdb.connect()
    clean_glob = (processed_dir / "yellow_tripdata_clean_2024-*.parquet").as_posix()
    raw_glob = (raw_dir / "yellow_tripdata_2024-*.parquet").as_posix()
    zones = (raw_dir / "taxi_zone_lookup.csv").as_posix()
    con.execute(f"CREATE VIEW clean AS SELECT * FROM read_parquet('{clean_glob}')")
    con.execute(f"CREATE VIEW raw AS SELECT * FROM read_parquet('{raw_glob}')")
    con.execute(f"CREATE VIEW zones AS SELECT * FROM read_csv('{zones}', header = true, "
                "nullstr = ['N/A', ''])")
    return con


def sample(con: duckdb.DuckDBPyConnection, view: str = "clean",
           rows: int = SAMPLE_ROWS) -> pd.DataFrame:
    """Reproducible random sample with derived duration (min) and speed (mph)."""
    return con.sql(f"""
        SELECT *,
               date_diff('second', tpep_pickup_datetime, tpep_dropoff_datetime) / 60.0
                   AS duration_min,
               CASE WHEN tpep_dropoff_datetime > tpep_pickup_datetime
                    THEN trip_distance / (date_diff('second', tpep_pickup_datetime,
                                                    tpep_dropoff_datetime) / 3600.0)
               END AS speed_mph
        FROM {view} USING SAMPLE reservoir({rows} ROWS) REPEATABLE ({SEED})
    """).df()


def save(fig: plt.Figure, name: str) -> Path:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURE_DIR / f"{name}.png"
    fig.savefig(path, bbox_inches="tight")
    return path


def _thousands(ax, axis: str = "y") -> None:
    fmt = plt.FuncFormatter(lambda v, _: f"{v:,.0f}")
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(fmt)


# --------------------------------------------------------------------------- 1. distributions
def plot_distributions(df: pd.DataFrame) -> plt.Figure:
    """Histograms of distance, fare and duration on a log x-axis (all are right-skewed)."""
    specs = [("trip_distance", "Trip distance (miles)", 0.01, 100),
             ("fare_amount", "Fare amount ($)", 1, 1000),
             ("duration_min", "Duration (minutes)", 0.1, 360)]
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.2))
    for ax, (col, label, lo, hi) in zip(axes, specs, strict=True):
        values = df[col].dropna()
        values = values[(values >= lo) & (values <= hi)]
        ax.hist(values, bins=np.logspace(np.log10(lo), np.log10(hi), 60),
                color=BLUE, edgecolor="white", linewidth=0.4)
        ax.set_xscale("log")
        ax.set_xlabel(label)
        ax.set_ylabel("Trips (sample)")
        ax.axvline(values.median(), color=INK, linewidth=1)
        ax.annotate(f"median {values.median():,.1f}", xy=(values.median(), ax.get_ylim()[1]),
                    xytext=(4, -12), textcoords="offset points", color=INK, fontsize=9)
        _thousands(ax)
    fig.suptitle("Distance, fare and duration are strongly right-skewed (log x-axis)",
                 x=0.01, ha="left", fontsize=13, fontweight="bold", color=INK)
    fig.tight_layout()
    return fig


# --------------------------------------------------------------------------- 2. fare vs distance
def plot_fare_vs_distance(df: pd.DataFrame) -> plt.Figure:
    """Hexbin density of fare against distance, with the standard meter rate."""
    d = df[(df["trip_distance"] <= 30) & (df["fare_amount"] <= 150)]
    fig, ax = plt.subplots(figsize=(10, 6))
    hb = ax.hexbin(d["trip_distance"], d["fare_amount"], gridsize=70, bins="log",
                   cmap=SEQUENTIAL, mincnt=1, linewidths=0)
    x = np.linspace(0, 30, 50)
    ax.plot(x, 3 + 3.5 * x, color=ORANGE, linewidth=2)
    # "\$" = a literal dollar sign (a bare "$" starts matplotlib math formatting)
    ax.annotate("Meter rate: \\$3 + \\$3.50/mile\n(no waiting time)", xy=(22, 3 + 3.5 * 22),
                xytext=(14, 115), color=INK, fontsize=9,
                arrowprops={"arrowstyle": "-", "color": INK_2, "linewidth": 0.8})
    ax.annotate("JFK flat fare \\$70", xy=(17, 70), xytext=(24, 52), color=INK, fontsize=9,
                arrowprops={"arrowstyle": "-", "color": INK_2, "linewidth": 0.8})
    cbar = fig.colorbar(hb, ax=ax)
    cbar.set_label("Trips per cell (log scale)", color=INK_2)
    cbar.outline.set_visible(False)
    ax.set_title("Fare rises linearly with distance, plus a flat-fare band at \\$70")
    ax.set_xlabel("Trip distance (miles)")
    ax.set_ylabel("Fare amount ($)")
    ax.set_xlim(0, 30)
    ax.set_ylim(0, 150)
    fig.tight_layout()
    return fig


# --------------------------------------------------------------------------- 3. tip % by payment
def tip_by_payment(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.sql("""
        SELECT payment_type,
               COUNT(*) AS trips,
               100 * AVG(tip_amount / fare_amount) AS avg_tip_pct,
               100 * AVG(CASE WHEN tip_amount > 0 THEN 1 ELSE 0 END) AS pct_with_tip
        FROM clean WHERE fare_amount > 0
        GROUP BY payment_type ORDER BY payment_type
    """).df().assign(payment=lambda t: t["payment_type"].map(PAYMENT_NAMES))


def plot_tip_by_payment(tips: pd.DataFrame) -> plt.Figure:
    t = tips.sort_values("avg_tip_pct")
    fig, ax = plt.subplots(figsize=(9, 4.5))
    bars = ax.barh(t["payment"], t["avg_tip_pct"], color=BLUE, height=0.6)
    for bar, pct, trips in zip(bars, t["avg_tip_pct"], t["trips"], strict=True):
        ax.annotate(f"{pct:.1f}%  ({trips / 1e6:.2f}M trips)" if trips >= 1e6
                    else f"{pct:.1f}%  ({trips:,.0f} trips)",
                    xy=(bar.get_width(), bar.get_y() + bar.get_height() / 2),
                    xytext=(5, 0), textcoords="offset points", va="center",
                    color=INK, fontsize=9)
    ax.set_title("Card riders tip about a quarter of the fare; cash tips are not recorded")
    ax.set_xlabel("Average tip as % of fare")
    ax.set_xlim(0, t["avg_tip_pct"].max() * 1.45)
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    return fig


# --------------------------------------------------------------------------- 4. hour x weekday
def hourly_weekday(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Average trips per hour-slot for each weekday (trips / number of such days)."""
    return con.sql("""
        WITH t AS (
            SELECT isodow(tpep_pickup_datetime) AS dow, hour(tpep_pickup_datetime) AS hr,
                   CAST(tpep_pickup_datetime AS DATE) AS d
            FROM clean
        )
        SELECT dow, hr, COUNT(*) / COUNT(DISTINCT d) AS avg_trips
        FROM t GROUP BY dow, hr ORDER BY dow, hr
    """).df()


def plot_hour_weekday_heatmap(hw: pd.DataFrame) -> plt.Figure:
    grid = hw.pivot(index="dow", columns="hr", values="avg_trips")
    fig, ax = plt.subplots(figsize=(13, 4.6))
    im = ax.imshow(grid.to_numpy(), aspect="auto", cmap=SEQUENTIAL)
    ax.set_yticks(range(7), DAY_NAMES)
    ax.set_xticks(range(0, 24, 2), [f"{h:02d}:00" for h in range(0, 24, 2)])
    ax.grid(False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    peak = hw.loc[hw["avg_trips"].idxmax()]
    # outline the peak cell with a white ring, and name it above the plot
    ax.add_patch(plt.Rectangle((peak.hr - 0.5, peak.dow - 1.5), 1, 1, fill=False,
                               edgecolor="white", linewidth=2))
    ax.text(1.0, 1.02, f"outlined: peak {DAY_NAMES[int(peak.dow) - 1]} "
            f"{int(peak.hr):02d}:00, {peak.avg_trips:,.0f} trips/hour",
            transform=ax.transAxes, ha="right", va="bottom", color=INK_2, fontsize=9)
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Average trips per hour", color=INK_2)
    cbar.outline.set_visible(False)
    ax.set_title("Demand peaks on weekday evenings; weekend nights stay busy after midnight")
    ax.set_xlabel("Pickup hour")
    ax.set_ylabel("Day of week")
    fig.tight_layout()
    return fig


# --------------------------------------------------------------------------- 5. borough
def demand_by_borough(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.sql("""
        SELECT COALESCE(z.Borough, 'Outside NYC') AS borough, COUNT(*) AS trips
        FROM clean c JOIN zones z ON z.LocationID = c.PULocationID
        GROUP BY 1 ORDER BY trips
    """).df().assign(share=lambda t: 100 * t["trips"] / t["trips"].sum())


def plot_demand_by_borough(boroughs: pd.DataFrame) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(9, 4.8))
    bars = ax.barh(boroughs["borough"], boroughs["trips"], color=BLUE, height=0.6)
    for bar, trips, share in zip(bars, boroughs["trips"], boroughs["share"], strict=True):
        ax.annotate(f"{trips / 1e6:.2f}M ({share:.1f}%)" if trips >= 1e6
                    else f"{trips:,.0f} ({share:.2f}%)",
                    xy=(bar.get_width(), bar.get_y() + bar.get_height() / 2),
                    xytext=(5, 0), textcoords="offset points", va="center",
                    color=INK, fontsize=9)
    ax.set_title("Manhattan accounts for almost 9 in 10 yellow-taxi pickups")
    ax.set_xlabel("Pickups, Jan-Jun 2024")
    ax.set_xlim(0, boroughs["trips"].max() * 1.3)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v / 1e6:.0f}M"))
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    return fig


# --------------------------------------------------------------------------- 6. outliers
def plot_outlier_boxplots(raw: pd.DataFrame, clean: pd.DataFrame) -> plt.Figure:
    """Raw vs cleaned box plots on a symmetric-log axis (shows negatives and extremes)."""
    specs = [("trip_distance", "Trip distance (miles)"),
             ("fare_amount", "Fare amount ($)"),
             ("duration_min", "Duration (minutes)")]
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.8))
    for ax, (col, label) in zip(axes, specs, strict=True):
        data = [raw[col].dropna(), clean[col].dropna()]
        bp = ax.boxplot(data, tick_labels=["Raw", "Cleaned"], widths=0.5, patch_artist=True,
                        flierprops={"marker": "o", "markersize": 2.5, "alpha": 0.25,
                                    "markeredgewidth": 0},
                        medianprops={"color": INK, "linewidth": 1.2},
                        whiskerprops={"color": INK_2}, capprops={"color": INK_2},
                        boxprops={"linewidth": 0})
        for patch, flier, color in zip(bp["boxes"], bp["fliers"], [GRAY, BLUE], strict=True):
            patch.set_facecolor(color)
            flier.set_markerfacecolor(color)
        ax.set_yscale("symlog", linthresh=1)
        ax.set_ylabel(label)
        ax.annotate(f"min {data[0].min():,.0f}\nmax {data[0].max():,.0f}",
                    xy=(0.03, 0.97), xycoords="axes fraction", va="top", fontsize=8.5,
                    color=INK_2)
    fig.suptitle("Cleaning removes negative and impossible values, but real long trips remain "
                 "(symmetric log y-axis)", x=0.01, ha="left", fontsize=13,
                 fontweight="bold", color=INK)
    fig.tight_layout()
    return fig


# --------------------------------------------------------------------------- 7. correlation
CORR_COLUMNS = {"trip_distance": "Distance", "duration_min": "Duration", "speed_mph": "Speed",
                "fare_amount": "Fare", "tip_amount": "Tip", "tolls_amount": "Tolls",
                "total_amount": "Total", "passenger_count": "Passengers"}


def plot_correlation(df: pd.DataFrame) -> plt.Figure:
    """Spearman correlation (rank-based: robust to the skew and outliers seen above)."""
    corr = df[list(CORR_COLUMNS)].rename(columns=CORR_COLUMNS).corr(method="spearman")
    fig, ax = plt.subplots(figsize=(8.5, 7))
    im = ax.imshow(corr.to_numpy(), cmap=DIVERGING, vmin=-1, vmax=1)
    labels = list(corr.columns)
    ax.set_xticks(range(len(labels)), labels, rotation=45, ha="right")
    ax.set_yticks(range(len(labels)), labels)
    ax.grid(False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    for i in range(len(labels)):
        for j in range(len(labels)):
            v = corr.iat[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=8.5,
                    color="white" if abs(v) > 0.6 else INK)
    cbar = fig.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label("Spearman correlation", color=INK_2)
    cbar.outline.set_visible(False)
    ax.set_title("Distance, duration, fare and total move together; passengers matter little")
    fig.tight_layout()
    return fig


# --------------------------------------------------------------------------- 8. monthly trend
def monthly_trend(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.sql("""
        SELECT date_trunc('month', tpep_pickup_datetime) AS month,
               COUNT(*) AS trips, SUM(total_amount) AS revenue
        FROM clean GROUP BY 1 ORDER BY 1
    """).df()


def plot_monthly_trend(m: pd.DataFrame) -> plt.Figure:
    """Trips and revenue as two panels (never two y-axes on one chart)."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.3))
    labels = m["month"].dt.strftime("%b")
    for ax, col, title, scale, unit in [
        (axes[0], "trips", "Trips per month", 1e6, "M"),
        (axes[1], "revenue", "Revenue per month", 1e6, "M $"),
    ]:
        ax.plot(labels, m[col] / scale, color=BLUE, linewidth=2, marker="o", markersize=7)
        ax.set_title(title, fontsize=11)
        ax.set_ylabel(f"{title.split()[0]} ({unit})")
        ax.set_ylim(0, (m[col] / scale).max() * 1.15)
        for i in (0, len(m) - 1, int(m[col].idxmax())):
            ax.annotate(f"{m[col].iat[i] / scale:.1f}", xy=(i, m[col].iat[i] / scale),
                        xytext=(0, 8), textcoords="offset points", ha="center",
                        color=INK, fontsize=9)
    fig.suptitle("Trips and revenue grow from winter to spring, peaking in May",
                 x=0.01, ha="left", fontsize=13, fontweight="bold", color=INK)
    fig.tight_layout()
    return fig


# --------------------------------------------------------------------------- 9. daily + rolling
def daily_trips(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    d = con.sql("""
        SELECT CAST(tpep_pickup_datetime AS DATE) AS day, COUNT(*) AS trips
        FROM clean GROUP BY 1 ORDER BY 1
    """).df()
    d["rolling_7d"] = d["trips"].rolling(7).mean()
    return d


def plot_daily_trips(d: pd.DataFrame) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(13, 4.5))
    ax.plot(d["day"], d["trips"], color="#9dc8f7", linewidth=1, label="Daily trips")
    ax.plot(d["day"], d["rolling_7d"], color=BLUE, linewidth=2, label="7-day average")
    low = d.loc[d["trips"].idxmin()]
    ax.annotate(f"lowest day: {low.day:%a %b %d} ({low.trips:,.0f})", xy=(low.day, low.trips),
                xytext=(12, -4), textcoords="offset points", color=INK, fontsize=9)
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b"))
    ax.set_title("Daily demand follows a weekly rhythm and dips around holidays")
    ax.set_ylabel("Trips per day")
    ax.set_ylim(0, d["trips"].max() * 1.1)
    _thousands(ax)
    ax.legend(loc="lower right")
    fig.tight_layout()
    return fig
