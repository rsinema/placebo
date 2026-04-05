import difflib
import statistics
from collections import defaultdict

from langchain_core.tools import tool

from placebo_analytics import db
from placebo_analytics.agent.nodes import _compute_pearson, _compute_slope, _safe_days
from placebo_analytics.models import Metric


async def _resolve_metric_by_name(metric_name: str) -> Metric | None:
    """Resolve a metric name to a Metric object with fuzzy matching.

    Simplified version of _resolve_metric in nodes.py — no state dependency,
    just name-based resolution for use in tools.
    """
    if not metric_name:
        return None
    metric = await db.get_metric_by_name(metric_name)
    if metric:
        return metric
    # Fuzzy match
    active_metrics = await db.get_active_metrics()
    name_variants: dict[str, str] = {}
    for m in active_metrics:
        name_variants[m.name.lower()] = m.name
        name_variants[m.name.replace("_", " ").lower()] = m.name
    candidates = difflib.get_close_matches(
        metric_name.lower(), name_variants.keys(), n=1, cutoff=0.6
    )
    if candidates:
        return await db.get_metric_by_name(name_variants[candidates[0]])
    return None


@tool
async def list_active_metrics() -> str:
    """List all active health metrics the user is tracking, with their names and types."""
    metrics = await db.get_active_metrics()
    if not metrics:
        return "No active metrics found."
    lines = [f"- {m.name} ({m.response_type})" for m in metrics]
    return "Active metrics:\n" + "\n".join(lines)


@tool
async def get_metric_summary(metric_name: str, days: int = 30) -> str:
    """Get summary statistics (average, min, max, std dev, count) for a metric over N days.
    Use this to understand a metric's baseline and variability."""
    days = _safe_days(days)
    metric = await _resolve_metric_by_name(metric_name)
    if not metric:
        return f"Metric '{metric_name}' not found. Use list_active_metrics to see available metrics."
    stats = await db.get_metric_stats(metric.id, days)
    if not stats or stats.get("avg_value") is None:
        return f"No numeric data for {metric.name} in the last {days} days."
    return (
        f"{metric.name} (last {days} days): "
        f"avg={stats['avg_value']:.2f}, min={stats['min_value']:.2f}, "
        f"max={stats['max_value']:.2f}, stddev={stats.get('stddev_value') or 0:.2f}, "
        f"n={stats['count']}"
    )


@tool
async def get_metric_trend(metric_name: str, days: int = 30) -> str:
    """Get the trend direction (improving/declining/stable), slope, and latest value for a metric.
    Use this to understand whether a metric is getting better or worse over time."""
    days = _safe_days(days)
    metric = await _resolve_metric_by_name(metric_name)
    if not metric:
        return f"Metric '{metric_name}' not found. Use list_active_metrics to see available metrics."
    points = await db.get_trend_points(metric.id, limit=min(days, 30))
    if len(points) < 2:
        return f"Not enough data for {metric.name} trend (need at least 2 data points, have {len(points)})."
    slope = _compute_slope(points)
    if slope > 0.05:
        direction = "improving"
    elif slope < -0.05:
        direction = "declining"
    else:
        direction = "stable"
    latest = points[-1]["value"]
    avg = sum(p["value"] for p in points) / len(points)
    return (
        f"{metric.name} trend (last {days} days): {direction} "
        f"(slope={slope:.4f}), latest={latest:.2f}, avg={avg:.2f}, "
        f"n={len(points)} data points"
    )


@tool
async def get_metric_correlation(
    metric_a_name: str, metric_b_name: str, days: int = 30
) -> str:
    """Compute the Pearson correlation between two metrics over N days.
    Returns r-value and number of paired observations. Use to test hypotheses about relationships."""
    days = _safe_days(days)
    metric_a = await _resolve_metric_by_name(metric_a_name)
    metric_b = await _resolve_metric_by_name(metric_b_name)
    if not metric_a:
        return f"Metric '{metric_a_name}' not found."
    if not metric_b:
        return f"Metric '{metric_b_name}' not found."
    pairs = await db.get_correlation_pairs(metric_a.id, metric_b.id, days)
    r = _compute_pearson(pairs)
    if r is None:
        return f"Not enough paired data between {metric_a.name} and {metric_b.name} (need at least 3 overlapping days, have {len(pairs)})."
    strength = "strong" if abs(r) >= 0.6 else "moderate" if abs(r) >= 0.3 else "weak"
    direction = "positive" if r > 0 else "negative"
    return (
        f"{metric_a.name} vs {metric_b.name}: r={r:.3f} ({strength} {direction}), "
        f"n={len(pairs)} paired days"
    )


@tool
async def get_all_correlations(days: int = 30) -> str:
    """Get the top 5 strongest correlations across all numeric metric pairs.
    Use this to discover unexpected relationships between metrics."""
    days = _safe_days(days)
    pairs = await db.get_all_numeric_metric_pairs(days)
    if not pairs:
        return "Not enough paired data to compute correlations."
    pair_data: dict[tuple, list] = defaultdict(list)
    for row in pairs:
        key = (row["metric_a_id"], row["metric_b_id"])
        pair_data[key].append((row["value_a"], row["value_b"]))
    correlations = []
    for (id_a, id_b), data in pair_data.items():
        if len(data) >= 3:
            r = _compute_pearson([{"value_a": d[0], "value_b": d[1]} for d in data])
            if r is not None:
                name_a = next(
                    (p["metric_a_name"] for p in pairs if p["metric_a_id"] == id_a),
                    str(id_a),
                )
                name_b = next(
                    (p["metric_b_name"] for p in pairs if p["metric_b_id"] == id_b),
                    str(id_b),
                )
                correlations.append((abs(r), r, name_a, name_b, len(data)))
    correlations.sort(reverse=True)
    top = correlations[:5]
    if not top:
        return "Not enough paired data points to rank correlations."
    lines = [f"Top correlations (last {days} days):"]
    for _, r, name_a, name_b, n in top:
        direction = "positive" if r > 0 else "negative"
        lines.append(f"- {name_a} vs {name_b}: r={r:.3f} ({direction}), n={n}")
    return "\n".join(lines)


@tool
async def get_period_comparison(metric_name: str, days: int = 7) -> str:
    """Compare a metric's stats for the current period vs the previous period of equal length.
    Default is 7 days (this week vs last week). Use for before/after or week-over-week analysis."""
    days = _safe_days(days)
    metric = await _resolve_metric_by_name(metric_name)
    if not metric:
        return f"Metric '{metric_name}' not found."
    comparison = await db.get_period_comparison(metric.id, days)
    this_w = comparison.get("this_week", {})
    last_w = comparison.get("last_week", {})
    if not this_w or not last_w:
        return f"Not enough data for {metric.name} period comparison."
    pct = "N/A"
    if last_w.get("avg_value"):
        pct_val = ((this_w["avg_value"] - last_w["avg_value"]) / last_w["avg_value"]) * 100
        pct = f"{pct_val:+.1f}%"
    return (
        f"{metric.name} period comparison ({days}-day periods):\n"
        f"- Current: avg={this_w.get('avg_value', 0):.2f}, n={this_w.get('count', 0)}\n"
        f"- Previous: avg={last_w.get('avg_value', 0):.2f}, n={last_w.get('count', 0)}\n"
        f"- Change: {pct}"
    )


@tool
async def get_consistency_info(metric_name: str, days: int = 30) -> str:
    """Get logging consistency and streak data for a metric: days with data, consistency %, longest streak.
    Use to assess adherence to tracking habits."""
    days = _safe_days(days)
    metric = await _resolve_metric_by_name(metric_name)
    if not metric:
        return f"Metric '{metric_name}' not found."
    c = await db.get_consistency(metric.id, days)
    return (
        f"{metric.name} consistency (last {days} days): "
        f"{c['days_with_data']}/{c['total_days']} days logged "
        f"({c['consistency_pct']:.1f}%), longest streak: {c['longest_streak']} days"
    )


@tool
async def list_experiments() -> str:
    """List all active experiments with their names, start dates, and hypotheses."""
    experiments = await db.get_active_experiments()
    if not experiments:
        return "No active experiments."
    lines = []
    for e in experiments:
        hyp = f" — hypothesis: {e.hypothesis}" if e.hypothesis else ""
        lines.append(f"- {e.name} (started {e.started_at.strftime('%Y-%m-%d')}{hyp})")
    return "Active experiments:\n" + "\n".join(lines)


@tool
async def get_experiment_results(experiment_name: str) -> str:
    """Get before/during metric comparisons for a specific experiment.
    Shows how each tracked metric changed since the experiment started."""
    experiments = await db.get_active_experiments()
    experiment = None
    for e in experiments:
        if experiment_name.lower() in e.name.lower():
            experiment = e
            break
    if not experiment:
        return f"Experiment '{experiment_name}' not found. Use list_experiments to see active experiments."
    comparisons = await db.get_experiment_metric_comparisons(experiment.id)
    if not comparisons:
        return f"No comparison data yet for experiment '{experiment.name}'."
    lines = [f"Experiment: {experiment.name} (started {experiment.started_at.strftime('%Y-%m-%d')})"]
    from collections import defaultdict as _dd

    by_metric: dict[str, dict] = _dd(dict)
    for row in comparisons:
        by_metric[row["metric_name"]][row["period"]] = row["avg_value"]
    for name, periods in by_metric.items():
        before = periods.get("before")
        during = periods.get("during")
        if before is not None and during is not None:
            change = during - before
            lines.append(f"- {name}: before={before:.2f}, during={during:.2f}, change={change:+.2f}")
        else:
            lines.append(f"- {name}: incomplete data")
    return "\n".join(lines)


@tool
async def get_boolean_metric_frequency(metric_name: str, days: int = 30) -> str:
    """Get true/false frequency breakdown for a boolean (yes/no) metric over N days."""
    days = _safe_days(days)
    metric = await _resolve_metric_by_name(metric_name)
    if not metric:
        return f"Metric '{metric_name}' not found."
    freq = await db.get_boolean_frequency(metric.id, days)
    if not freq or freq["total"] == 0:
        return f"No boolean data for {metric.name} in the last {days} days."
    true_pct = freq["true_count"] / freq["total"] * 100
    return (
        f"{metric.name} (last {days} days): "
        f"true={freq['true_count']} ({true_pct:.0f}%), "
        f"false={freq['false_count']} ({100 - true_pct:.0f}%), "
        f"total={freq['total']}"
    )


ALL_TOOLS = [
    list_active_metrics,
    get_metric_summary,
    get_metric_trend,
    get_metric_correlation,
    get_all_correlations,
    get_period_comparison,
    get_consistency_info,
    list_experiments,
    get_experiment_results,
    get_boolean_metric_frequency,
]
