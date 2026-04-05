import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
from io import BytesIO

from placebo_analytics.models import Metric

# Color palette matching dashboard aesthetics
_COLORS = {
    "primary": "#4F46E5",
    "secondary": "#10B981",
    "tertiary": "#F59E0B",
    "quaternary": "#EF4444",
    "background": "#FFFFFF",
    "grid": "#E5E7EB",
    "text": "#1F2937",
    "muted": "#6B7280",
}

_PALETTE = ["#4F46E5", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#EC4899", "#06B6D4", "#84CC16"]


def _setup_figure(figsize: tuple = (10, 5)) -> tuple:
    """Create a figure with white background and clean styling."""
    fig, ax = plt.subplots(figsize=figsize, facecolor=_COLORS["background"])
    ax.set_facecolor(_COLORS["background"])
    ax.grid(True, color=_COLORS["grid"], linestyle="--", linewidth=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(_COLORS["grid"])
    ax.spines["bottom"].set_color(_COLORS["grid"])
    ax.tick_params(colors=_COLORS["muted"])
    ax.set_xlabel("", color=_COLORS["muted"])
    ax.set_ylabel("", color=_COLORS["muted"])
    return fig, ax


def _save_to_bytes(fig) -> bytes:
    """Save figure to PNG bytes, close figure to free memory."""
    buf = BytesIO()
    try:
        fig.savefig(buf, format="png", dpi=100, bbox_inches="tight", facecolor=_COLORS["background"])
        buf.seek(0)
        return buf.read()
    finally:
        plt.close(fig)


def metric_time_series(
    metric: Metric, responses: list[dict], trend_days: int = 7
) -> bytes:
    """Line chart with rolling average for a single metric."""
    if not responses:
        return _empty_chart(f"No data for {metric.name}")

    dates = [r["date_val"] if isinstance(r.get("date_val"), datetime) else r["date"] for r in responses]
    values = [float(r["avg_value"]) for r in responses]

    fig, ax = _setup_figure()

    # Raw values line
    ax.plot(dates, values, "o-", color=_COLORS["primary"], linewidth=1.5, markersize=3, alpha=0.4, label="Daily avg")

    # Rolling average
    if len(values) >= trend_days:
        rolling = []
        rolling_dates = []
        for i in range(trend_days - 1, len(values)):
            rolling.append(sum(values[i - trend_days + 1 : i + 1]) / trend_days)
            rolling_dates.append(dates[i])
        ax.plot(rolling_dates, rolling, "-", color=_COLORS["secondary"], linewidth=2, label=f"{trend_days}-day rolling avg")

    ax.set_title(metric.name.replace("_", " ").title(), color=_COLORS["text"], fontsize=13, fontweight="bold")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")
    ax.legend(frameon=False, loc="upper right")
    fig.tight_layout()
    return _save_to_bytes(fig)


def experiment_comparison(comparison_data: dict) -> bytes:
    """Grouped bar chart comparing before vs. during experiment."""
    if not comparison_data:
        return _empty_chart("No experiment data")

    labels = list(comparison_data.keys())
    before_vals = [comparison_data[k].get("avg_value") for k in labels]
    during_vals = [comparison_data[k].get("avg_value") for k in labels]

    fig, ax = _setup_figure(figsize=(10, 5))
    x = range(len(labels))
    width = 0.35

    ax.bar([i - width / 2 for i in x], before_vals, width, label="Before", color=_COLORS["quaternary"], alpha=0.8)
    ax.bar([i + width / 2 for i in x], during_vals, width, label="During", color=_COLORS["secondary"], alpha=0.8)

    ax.set_xticks(list(x))
    ax.set_xticklabels([k.title() for k in labels], color=_COLORS["text"])
    ax.set_title("Experiment: Before vs. During", color=_COLORS["text"], fontsize=13, fontweight="bold")
    ax.legend(frameon=False)
    fig.tight_layout()
    return _save_to_bytes(fig)


def correlation_scatter(
    points: list[dict], metric_a_name: str, metric_b_name: str, r_value: float | None = None
) -> bytes:
    """Scatter plot with trend line for two metrics."""
    if not points:
        return _empty_chart("No paired data available")

    vals_a = [p["value_a"] for p in points]
    vals_b = [p["value_b"] for p in points]

    fig, ax = _setup_figure()

    ax.scatter(vals_a, vals_b, color=_COLORS["primary"], alpha=0.6, s=40)

    # Trend line
    if len(vals_a) >= 2:
        import numpy as np
        z = np.polyfit(vals_a, vals_b, 1)
        p = np.poly1d(z)
        x_line = [min(vals_a), max(vals_a)]
        ax.plot(x_line, [p(x) for x in x_line], "--", color=_COLORS["quaternary"], linewidth=1.5, alpha=0.8)

    r_label = f"r = {r_value:.3f}" if r_value is not None else ""
    ax.set_xlabel(metric_a_name.replace("_", " ").title(), color=_COLORS["text"])
    ax.set_ylabel(metric_b_name.replace("_", " ").title(), color=_COLORS["text"])
    ax.set_title(f"Correlation: {metric_a_name} vs {metric_b_name} {r_label}", color=_COLORS["text"], fontsize=12, fontweight="bold")
    fig.tight_layout()
    return _save_to_bytes(fig)


def week_comparison(
    this_week: dict, last_week: dict, metrics: list[str]
) -> bytes:
    """Side-by-side grouped bar chart comparing this week vs. last week."""
    if not this_week and not last_week:
        return _empty_chart("No period data available")

    labels = metrics or list(set(list(this_week.keys()) + list(last_week.keys())))
    tw_vals = [this_week.get(m, {}).get("avg_value") for m in labels]
    lw_vals = [last_week.get(m, {}).get("avg_value") for m in labels]

    fig, ax = _setup_figure(figsize=(10, 5))
    x = range(len(labels))
    width = 0.35

    ax.bar([i - width / 2 for i in x], lw_vals, width, label="Last week", color=_COLORS["muted"], alpha=0.8)
    ax.bar([i + width / 2 for i in x], tw_vals, width, label="This week", color=_COLORS["primary"], alpha=0.8)

    ax.set_xticks(list(x))
    ax.set_xticklabels([m.replace("_", " ").title() for m in labels], color=_COLORS["text"], rotation=30, ha="right")
    ax.set_title("This Week vs. Last Week", color=_COLORS["text"], fontsize=13, fontweight="bold")
    ax.legend(frameon=False)
    fig.tight_layout()
    return _save_to_bytes(fig)


def multi_metric_overview(metric_summaries: list[dict]) -> bytes:
    """Grid of mini time-series charts for multiple metrics."""
    if not metric_summaries:
        return _empty_chart("No metrics to display")

    n = len(metric_summaries)
    cols = min(3, n)
    rows = (n + cols - 1) // cols

    fig, axes = plt.subplots(rows, cols, figsize=(12, 3.5 * rows), facecolor=_COLORS["background"])
    if n == 1:
        axes = [axes]
    else:
        axes = axes.flatten() if hasattr(axes, "flatten") else axes

    for idx, summary in enumerate(metric_summaries):
        ax = axes[idx]
        ax.set_facecolor(_COLORS["background"])
        ax.grid(True, color=_COLORS["grid"], linestyle="--", linewidth=0.5)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        name = summary.get("name", "Metric").replace("_", " ").title()
        avg = summary.get("avg_value")
        min_v = summary.get("min_value")
        max_v = summary.get("max_value")
        count = summary.get("count", 0)
        color = _PALETTE[idx % len(_PALETTE)]
        avg_str = f"{avg:.1f}" if avg is not None else "N/A"
        min_str = f"{min_v:.1f}" if min_v is not None else "N/A"
        max_str = f"{max_v:.1f}" if max_v is not None else "N/A"
        ax.set_title(f"{name}\navg={avg_str} | min={min_str} | max={max_str} | n={count}", color=color, fontsize=9, fontweight="bold")
        ax.set_xticks([])
        ax.set_yticks([])

    # Hide unused subplots
    for idx in range(n, len(axes)):
        axes[idx].set_visible(False)

    fig.tight_layout(pad=2)
    return _save_to_bytes(fig)


def _empty_chart(message: str) -> bytes:
    """Return a blank chart with a message."""
    fig, ax = plt.subplots(figsize=(10, 5), facecolor=_COLORS["background"])
    ax.set_facecolor(_COLORS["background"])
    ax.text(0.5, 0.5, message, ha="center", va="center", color=_COLORS["muted"], fontsize=14)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    fig.tight_layout()
    return _save_to_bytes(fig)
