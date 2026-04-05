import difflib
import json
import logging
import statistics

from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph.message import RemoveMessage

from placebo_analytics.agent.prompts import (
    CLASSIFY_ANALYTICS_INTENT,
    GENERAL_ANALYTICS_PROMPT,
    GENERATE_STREAK_SUMMARY,
    SYNTHESIZE_CORRELATION,
    SYNTHESIZE_EXPERIMENT_ANALYSIS,
    SYNTHESIZE_METRIC_SUMMARY,
    SYNTHESIZE_PERIOD_COMPARISON,
    SYNTHESIZE_TREND,
)
from placebo_analytics.agent.state import AnalyticsState
from placebo_analytics import charts
from placebo_analytics import db
from placebo_analytics.config import settings

logger = logging.getLogger(__name__)

_MOONSHOT_BASE_URL = "https://api.moonshot.ai/v1"

_llm = ChatOpenAI(
    model="kimi-k2-0905-preview",
    base_url=_MOONSHOT_BASE_URL,
    api_key=settings.moonshot_api_key,
    max_tokens=256,
)

_llm_general = ChatOpenAI(
    model="kimi-k2-0905-preview",
    base_url=_MOONSHOT_BASE_URL,
    api_key=settings.moonshot_api_key,
    max_tokens=1024,
)


def _parse_json(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0]
    return json.loads(text.strip())


def _compute_slope(points: list[dict]) -> float:
    """Compute linear regression slope from (days_since_epoch, value) pairs."""
    if len(points) < 2:
        return 0.0
    x = [p["days_since_epoch"] for p in points]
    y = [p["value"] for p in points]
    try:
        return statistics.correlation(x, y) * (statistics.stdev(y) / statistics.stdev(x)) if statistics.stdev(x) > 0 else 0.0
    except Exception:
        return 0.0


def _compute_pearson(points: list[dict]) -> float | None:
    """Compute Pearson correlation coefficient from paired data."""
    if len(points) < 3:
        return None
    vals_a = [p["value_a"] for p in points]
    vals_b = [p["value_b"] for p in points]
    try:
        return statistics.correlation(vals_a, vals_b)
    except Exception:
        return None


def _safe_days(value: object, default: int = 30) -> int:
    """Coerce an LLM-provided 'days' value to a sane positive integer."""
    try:
        days = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(days, 365))


MAX_MESSAGES = 10


async def _resolve_metric(
    metric_name: str,
    state: AnalyticsState,
) -> tuple:
    """Resolve a metric name to a Metric object with fuzzy matching.

    Returns (metric, error_message). If metric is None, error_message
    contains a user-friendly clarification with available options.
    """
    active_metrics = await db.get_active_metrics()
    active_names = [m.name for m in active_metrics]

    # Step 1: Exact match via DB (case-insensitive)
    if metric_name:
        metric = await db.get_metric_by_name(metric_name)
        if metric:
            return metric, None

        # Step 2: Fuzzy match against active metric names
        name_variants: dict[str, str] = {}
        for n in active_names:
            name_variants[n.lower()] = n
            name_variants[n.replace("_", " ").lower()] = n

        candidates = difflib.get_close_matches(
            metric_name.lower(),
            name_variants.keys(),
            n=1,
            cutoff=0.6,
        )
        if candidates:
            real_name = name_variants[candidates[0]]
            metric = await db.get_metric_by_name(real_name)
            if metric:
                return metric, None

    # Step 3: Substring scan of user message
    last_msg = state["messages"][-1].content.lower() if state.get("messages") else ""
    for m in active_metrics:
        if m.name.lower() in last_msg or m.name.replace("_", " ").lower() in last_msg:
            return m, None

    # Step 4: No match — return clarification with available metrics
    if active_names:
        names_list = ", ".join(f"**{n}**" for n in active_names)
        error = f"I couldn't find that metric. Here are your active metrics: {names_list}"
    else:
        error = "You don't have any active metrics yet."

    return None, error


def _metric_not_found_response(error_msg: str) -> dict:
    """Build a standard handler return dict for metric-not-found cases."""
    return {
        "response_text": error_msg,
        "messages": [_build_ai_message(error_msg, ["Show me all my metrics"])],
        "chart_bytes": None,
        "suggested_followups": ["Show me all my metrics"],
    }


def _build_ai_message(response_text: str, followups: list[str]) -> AIMessage:
    """Build an AIMessage combining the response text and suggested follow-ups."""
    content = response_text
    if followups:
        content += "\n\nSuggested follow-ups: " + " | ".join(followups)
    return AIMessage(content=content)


# ---------------------------------------------------------------------------
# Reset turn (entry node — clears stale per-turn fields, trims messages)
# ---------------------------------------------------------------------------


async def reset_turn(state: AnalyticsState) -> dict:
    updates: dict = {
        "intent": "",
        "response_text": "",
        "chart_bytes": None,
        "suggested_followups": [],
        "classification_confidence": 0.0,
        "alternative_intents": [],
    }
    messages = state.get("messages", [])
    if len(messages) > MAX_MESSAGES:
        to_remove = messages[:-MAX_MESSAGES]
        updates["messages"] = [RemoveMessage(id=m.id) for m in to_remove]
    return updates


# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------


def _build_conversation_context(messages: list) -> str:
    """Build a concise context string from prior messages for the classifier."""
    if len(messages) <= 1:
        return "(no prior context)"
    context_lines = []
    for msg in messages[:-1]:
        role = "User" if isinstance(msg, HumanMessage) else "Assistant"
        # Truncate long messages to keep classification prompt manageable
        content = msg.content[:300]
        context_lines.append(f"{role}: {content}")
    # Keep last 8 context lines (4 exchanges)
    return "\n".join(context_lines[-8:])


async def classify_intent(state: AnalyticsState) -> dict:
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""
    conversation_context = _build_conversation_context(messages)

    active_metrics = await db.get_active_metrics()
    available_metrics = ", ".join(m.name for m in active_metrics) if active_metrics else "(no metrics configured)"

    prompt = CLASSIFY_ANALYTICS_INTENT.format(
        conversation_context=conversation_context,
        available_metrics=available_metrics,
    )
    resp = await _llm.ainvoke(
        [SystemMessage(content=prompt), HumanMessage(content=last_msg)]
    )
    try:
        result = _parse_json(resp.content)
        confidence = float(result.get("confidence", 0.8))
        alternatives = result.get("alternative_intents", [])
        return {
            "intent": result.get("intent", "general"),
            "_params": result.get("parameters", {}),
            "classification_confidence": min(max(confidence, 0.0), 1.0),
            "alternative_intents": alternatives[:3],
        }
    except (json.JSONDecodeError, KeyError, ValueError):
        logger.warning("Failed to parse analytics intent: %s", resp.content)
        return {
            "intent": "general",
            "_params": {},
            "classification_confidence": 0.0,
            "alternative_intents": [],
        }


# ---------------------------------------------------------------------------
# Clarification (low-confidence routing)
# ---------------------------------------------------------------------------


_INTENT_DESCRIPTIONS = {
    "metric_summary": "a summary of a specific metric",
    "trend": "the trend of a metric over time",
    "correlation": "correlation between two metrics",
    "experiment_analysis": "analysis of an experiment",
    "multi_metric_overview": "an overview of all metrics",
    "period_comparison": "comparing time periods",
    "streak": "consistency / streaks",
    "correlation_ranking": "strongest correlations across metrics",
    "boolean_frequency": "frequency of a yes/no metric",
    "general": "a general analytics question",
}


async def handle_clarification(state: AnalyticsState) -> dict:
    """Ask the user to clarify when classification confidence is low."""
    intent = state.get("intent", "")
    alternatives = state.get("alternative_intents", [])

    candidates = [intent] + [a.get("intent", "") for a in alternatives if a.get("intent")]
    seen: set[str] = set()
    unique: list[str] = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            unique.append(c)

    options = []
    for i, c in enumerate(unique[:3], 1):
        desc = _INTENT_DESCRIPTIONS.get(c, c)
        options.append(f"{i}. {desc}")

    text = "I'm not quite sure what you're looking for. Did you mean:\n" + "\n".join(options) + "\n\nCould you rephrase or be more specific?"

    return {
        "response_text": text,
        "messages": [_build_ai_message(text, [])],
        "chart_bytes": None,
        "suggested_followups": [],
    }


# ---------------------------------------------------------------------------
# Metric summary
# ---------------------------------------------------------------------------


async def handle_metric_summary(state: AnalyticsState) -> dict:
    params = state.get("_params", {})
    metric_name = params.get("metric_name", "")
    days = _safe_days(params.get("days", 30))

    metric, error = await _resolve_metric(metric_name, state)
    if error:
        return _metric_not_found_response(error)
    if not metric:
        return _metric_not_found_response("Which metric would you like a summary of? Try something like 'summarize my sleep data'.")

    stats = await db.get_metric_stats(metric.id, days)
    rolling = await db.get_rolling_avg(metric.id, days)
    chart_bytes = None

    if rolling and metric.response_type == "numeric":
        chart_bytes = charts.metric_time_series(metric, rolling)
    elif metric.response_type == "boolean":
        freq = await db.get_boolean_frequency(metric.id, days)
        stats = freq if freq else stats

    if stats and stats.get("avg_value") is not None:
        prompt = SYNTHESIZE_METRIC_SUMMARY.format(
            metric_name=metric.name,
            days=days,
            avg=stats["avg_value"] or 0,
            min=stats["min_value"] or 0,
            max=stats["max_value"] or 0,
            stddev=stats.get("stddev_value") or 0,
            count=stats.get("count") or 0,
        )
    else:
        prompt = SYNTHESIZE_METRIC_SUMMARY.format(
            metric_name=metric.name, days=days, avg=0, min=0, max=0, stddev=0, count=0
        )

    try:
        resp = await _llm_general.ainvoke([HumanMessage(content=prompt)])
        parsed = _parse_json(resp.content)
        summary = parsed.get("summary", "Here's what I found.")
    except Exception:
        summary = f"Over the last {days} days, **{metric.name}** has an average of **{stats['avg_value']:.1f}** with {stats['count']} data points." if stats and stats.get("avg_value") else "Not enough data."

    followups = [f"See the 30-day trend for {metric.name}?", f"Compare {metric.name} to last week?"]
    return {
        "response_text": summary,
        "messages": [_build_ai_message(summary, followups)],
        "chart_bytes": chart_bytes,
        "suggested_followups": followups,
    }


# ---------------------------------------------------------------------------
# Trend
# ---------------------------------------------------------------------------


async def handle_trend(state: AnalyticsState) -> dict:
    params = state.get("_params", {})
    metric_name = params.get("metric_name", "")
    days = _safe_days(params.get("days", 30))

    metric, error = await _resolve_metric(metric_name, state)
    if error:
        return _metric_not_found_response(error)
    if not metric:
        return _metric_not_found_response("Which metric's trend do you want to see?")

    points = await db.get_trend_points(metric.id, limit=min(days, 30))
    rolling = await db.get_rolling_avg(metric.id, days)
    chart_bytes = charts.metric_time_series(metric, rolling) if rolling else None

    slope = _compute_slope(points)
    if slope > 0.05:
        direction = "improving"
    elif slope < -0.05:
        direction = "declining"
    else:
        direction = "stable"

    latest = points[-1]["value"] if points else 0
    rolling_avg = sum(p["value"] for p in points) / len(points) if points else 0

    try:
        prompt = SYNTHESIZE_TREND.format(
            metric_name=metric.name,
            days=days,
            direction=direction,
            slope=slope,
            latest=latest,
            rolling_avg=rolling_avg,
        )
        resp = await _llm_general.ainvoke([HumanMessage(content=prompt)])
        parsed = _parse_json(resp.content)
        summary = parsed.get("summary", f"Trend is **{direction}**.")
    except Exception:
        summary = f"Over the last {days} days, **{metric.name}** appears to be **{direction}**."

    followups = [f"Get a full summary of {metric.name}?", f"Compare {metric.name} this week to last week?"]
    return {
        "response_text": summary,
        "messages": [_build_ai_message(summary, followups)],
        "chart_bytes": chart_bytes,
        "suggested_followups": followups,
    }


# ---------------------------------------------------------------------------
# Correlation
# ---------------------------------------------------------------------------


async def handle_correlation(state: AnalyticsState) -> dict:
    params = state.get("_params", {})
    metric_a_name = params.get("metric_name", "")
    metric_b_name = params.get("metric_b_name", "")

    metric_a, error_a = await _resolve_metric(metric_a_name, state)
    metric_b, error_b = await _resolve_metric(metric_b_name, state)

    if not metric_a or not metric_b:
        error = error_a or error_b or "Which two metrics do you want to check for correlation?"
        return _metric_not_found_response(error)

    pairs = await db.get_correlation_pairs(metric_a.id, metric_b.id, days=30)
    r_value = _compute_pearson(pairs)
    chart_bytes = charts.correlation_scatter(pairs, metric_a.name, metric_b.name, r_value) if pairs else None

    if r_value is not None:
        try:
            prompt = SYNTHESIZE_CORRELATION.format(
                metric_a_name=metric_a.name,
                metric_b_name=metric_b.name,
                r_value=r_value,
                n_pairs=len(pairs),
            )
            resp = await _llm_general.ainvoke([HumanMessage(content=prompt)])
            parsed = _parse_json(resp.content)
            summary = parsed.get("summary", f"Correlation r = {r_value:.3f}")
        except Exception:
            summary = f"**{metric_a.name}** vs **{metric_b.name}**: r = **{r_value:.3f}**"
    else:
        summary = f"Not enough paired data to compute correlation between **{metric_a.name}** and **{metric_b.name}**."

    followups = ["See the top correlations across all my metrics?", "Get a full overview of all my metrics?"]
    return {
        "response_text": summary,
        "messages": [_build_ai_message(summary, followups)],
        "chart_bytes": chart_bytes,
        "suggested_followups": followups,
    }


# ---------------------------------------------------------------------------
# Experiment analysis
# ---------------------------------------------------------------------------


async def handle_experiment_analysis(state: AnalyticsState) -> dict:
    params = state.get("_params", {})
    experiment_name = params.get("experiment_name", "")

    active_exps = await db.get_active_experiments()
    if not active_exps:
        text = "No active experiments. Start one with the check-in bot first!"
        return {
            "response_text": text,
            "messages": [_build_ai_message(text, [])],
            "chart_bytes": None,
            "suggested_followups": [],
        }

    experiment = None
    if experiment_name:
        for e in active_exps:
            if experiment_name.lower() in e.name.lower():
                experiment = e
                break

    if not experiment:
        experiment = active_exps[0]  # Default to first active

    comparisons = await db.get_experiment_metric_comparisons(experiment.id)
    if not comparisons:
        text = f"Experiment **{experiment.name}** has no data yet."
        return {
            "response_text": text,
            "messages": [_build_ai_message(text, [])],
            "chart_bytes": None,
            "suggested_followups": [],
        }

    chart_bytes = None
    try:
        from collections import defaultdict
        comp_dict: dict = defaultdict(dict)
        for row in comparisons:
            comp_dict[row["metric_name"]][row["period"]] = row["avg_value"]
        chart_bytes = charts.experiment_comparison(comp_dict)
    except Exception:
        pass

    try:
        prompt = SYNTHESIZE_EXPERIMENT_ANALYSIS.format(
            experiment_name=experiment.name,
            started_at=experiment.started_at.strftime("%Y-%m-%d"),
            comparisons=repr(comparisons),
        )
        resp = await _llm_general.ainvoke([HumanMessage(content=prompt)])
        parsed = _parse_json(resp.content)
        verdict = parsed.get("verdict", "")
        summary = parsed.get("summary", "")
        response_text = f"**Experiment: {experiment.name}**\n\n{verdict}\n\n{summary}"
    except Exception:
        response_text = f"**Experiment: {experiment.name}**\n\nAnalysis: {comparisons}"

    followups = [f"See {experiment.name} metrics over time?", "Start a new experiment?"]
    return {
        "response_text": response_text,
        "messages": [_build_ai_message(response_text, followups)],
        "chart_bytes": chart_bytes,
        "suggested_followups": followups,
    }


# ---------------------------------------------------------------------------
# Multi-metric overview
# ---------------------------------------------------------------------------


async def handle_multi_metric_overview(state: AnalyticsState) -> dict:
    params = state.get("_params", {})
    days = params.get("days", 7)

    metrics = await db.get_active_metrics()
    if not metrics:
        text = "No active metrics to analyze."
        return {
            "response_text": text,
            "messages": [_build_ai_message(text, [])],
            "chart_bytes": None,
            "suggested_followups": [],
        }

    metric_ids = [m.id for m in metrics]
    summaries = await db.get_multi_metric_summary(metric_ids, days)
    chart_bytes = charts.multi_metric_overview(summaries) if summaries else None

    lines = []
    for s in summaries:
        avg = s.get("avg_value")
        if avg is not None:
            lines.append(f"• **{s['name']}**: avg {avg:.1f} ({s['count']} entries)")
        else:
            lines.append(f"• **{s['name']}**: no data")

    response_text = f"**Overview — last {days} days:**\n" + "\n".join(lines)
    if len(lines) > 5:
        response_text += "\n\n_Want more detail on any specific metric?_"

    followups = ["See trends for a specific metric?", "Compare this week to last week?"]
    return {
        "response_text": response_text,
        "messages": [_build_ai_message(response_text, followups)],
        "chart_bytes": chart_bytes,
        "suggested_followups": followups,
    }


# ---------------------------------------------------------------------------
# Period comparison
# ---------------------------------------------------------------------------


async def handle_period_comparison(state: AnalyticsState) -> dict:
    params = state.get("_params", {})
    metric_name = params.get("metric_name", "")
    days = params.get("days", 7)

    metric, error = await _resolve_metric(metric_name, state)
    if error:
        return _metric_not_found_response(error)
    if not metric:
        return _metric_not_found_response("Which metric do you want to compare?")

    comparison = await db.get_period_comparison(metric.id, days)
    chart_bytes = charts.week_comparison(
        comparison.get("this_week", {}),
        comparison.get("last_week", {}),
        [metric.name],
    ) if comparison else None

    this_w = comparison.get("this_week", {})
    last_w = comparison.get("last_week", {})

    if this_w and last_w and last_w.get("avg_value"):
        pct = ((this_w["avg_value"] - last_w["avg_value"]) / last_w["avg_value"]) * 100
        pct_str = f"+{pct:.1f}%" if pct >= 0 else f"{pct:.1f}%"
    else:
        pct_str = "N/A"

    try:
        prompt = SYNTHESIZE_PERIOD_COMPARISON.format(
            metric_name=metric.name,
            this_avg=this_w.get("avg_value") or 0,
            this_min=this_w.get("min_value") or 0,
            this_max=this_w.get("max_value") or 0,
            this_count=this_w.get("count") or 0,
            last_avg=last_w.get("avg_value") or 0,
            last_min=last_w.get("min_value") or 0,
            last_max=last_w.get("max_value") or 0,
            last_count=last_w.get("count") or 0,
            pct_change=pct,
        )
        resp = await _llm_general.ainvoke([HumanMessage(content=prompt)])
        parsed = _parse_json(resp.content)
        summary = parsed.get("summary", "")
    except Exception:
        summary = f"**{metric.name}** changed by **{pct_str}** this week vs. last week."

    followups = [f"Get the full {metric.name} trend?", "See all metrics compared?"]
    return {
        "response_text": summary,
        "messages": [_build_ai_message(summary, followups)],
        "chart_bytes": chart_bytes,
        "suggested_followups": followups,
    }


# ---------------------------------------------------------------------------
# Streak / consistency
# ---------------------------------------------------------------------------


async def handle_streak(state: AnalyticsState) -> dict:
    params = state.get("_params", {})
    metric_name = params.get("metric_name", "")
    days = _safe_days(params.get("days", 30))

    metric, error = await _resolve_metric(metric_name, state)
    if error:
        return _metric_not_found_response(error)
    if not metric:
        return _metric_not_found_response("Which metric's consistency do you want to check?")

    consistency = await db.get_consistency(metric.id, days)

    try:
        prompt = GENERATE_STREAK_SUMMARY.format(
            metric_name=metric.name,
            days_with_data=consistency["days_with_data"],
            total_days=consistency["total_days"],
            consistency_pct=consistency["consistency_pct"],
            longest_streak=consistency["longest_streak"],
        )
        resp = await _llm_general.ainvoke([HumanMessage(content=prompt)])
        parsed = _parse_json(resp.content)
        summary = parsed.get("summary", "")
    except Exception:
        summary = (
            f"**{metric.name}** consistency over {days} days: "
            f"**{consistency['days_with_data']}/{consistency['total_days']}** days logged "
            f"({consistency['consistency_pct']}% consistency, longest streak **{consistency['longest_streak']}** days)."
        )

    followups = [f"See trends for {metric.name}?", "Get an overview of all metrics?"]
    return {
        "response_text": summary,
        "messages": [_build_ai_message(summary, followups)],
        "chart_bytes": None,
        "suggested_followups": followups,
    }


# ---------------------------------------------------------------------------
# Correlation ranking
# ---------------------------------------------------------------------------


async def handle_correlation_ranking(state: AnalyticsState) -> dict:
    params = state.get("_params", {})
    days = _safe_days(params.get("days", 30))

    pairs = await db.get_all_numeric_metric_pairs(days)
    if not pairs:
        text = "Not enough paired data to compute correlations."
        return {
            "response_text": text,
            "messages": [_build_ai_message(text, [])],
            "chart_bytes": None,
            "suggested_followups": [],
        }

    from collections import defaultdict

    pair_data: dict[tuple, list] = defaultdict(list)
    for row in pairs:
        key = (row["metric_a_id"], row["metric_b_id"])
        pair_data[key].append((row["value_a"], row["value_b"]))

    correlations = []
    for (id_a, id_b), data in pair_data.items():
        if len(data) >= 3:
            r = _compute_pearson([{"value_a": d[0], "value_b": d[1]} for d in data])
            if r is not None:
                # Get names from first pair
                name_a = next((p["metric_a_name"] for p in pairs if p["metric_a_id"] == id_a), str(id_a))
                name_b = next((p["metric_b_name"] for p in pairs if p["metric_b_id"] == id_b), str(id_b))
                correlations.append((abs(r), r, name_a, name_b, len(data)))

    correlations.sort(reverse=True)
    top = correlations[:5]

    if not top:
        text = "Not enough paired data points to rank correlations."
        return {
            "response_text": text,
            "messages": [_build_ai_message(text, [])],
            "chart_bytes": None,
            "suggested_followups": [],
        }

    lines = [f"**Top correlations (|r|, last {days} days):**\n"]
    for abs_r, r, name_a, name_b, n in top:
        direction = "↑↑" if r > 0 else "↑↓"
        lines.append(f"• {name_a} ↔ {name_b}: r={r:.2f} ({direction}) — {n} paired days")

    response_text = "\n".join(lines)
    response_text += "\n\n_Note: correlation ≠ causation._"

    followups = ["See the scatter plot for the strongest correlation?", "Get an overview of all metrics?"]
    return {
        "response_text": response_text,
        "messages": [_build_ai_message(response_text, followups)],
        "chart_bytes": None,
        "suggested_followups": followups,
    }


# ---------------------------------------------------------------------------
# Boolean frequency
# ---------------------------------------------------------------------------


async def handle_boolean_frequency(state: AnalyticsState) -> dict:
    params = state.get("_params", {})
    metric_name = params.get("metric_name", "")
    days = _safe_days(params.get("days", 30))

    metric, error = await _resolve_metric(metric_name, state)
    if error:
        return _metric_not_found_response(error)
    if not metric:
        return _metric_not_found_response("Which boolean metric do you want to check?")

    freq = await db.get_boolean_frequency(metric.id, days)
    if not freq or freq["total"] == 0:
        text = f"No boolean data found for **{metric_name}**."
        return {
            "response_text": text,
            "messages": [_build_ai_message(text, [])],
            "chart_bytes": None,
            "suggested_followups": [],
        }

    true_pct = freq["true_count"] / freq["total"] * 100 if freq["total"] > 0 else 0
    false_pct = freq["false_count"] / freq["total"] * 100 if freq["total"] > 0 else 0

    summary = (
        f"**{metric.name}** (last {days} days):\n"
        f"• True: {freq['true_count']} days ({true_pct:.0f}%)\n"
        f"• False: {freq['false_count']} days ({false_pct:.0f}%)\n"
        f"• Total: {freq['total']} entries"
    )

    followups = [f"See the trend for {metric.name}?", "Get a full overview?"]
    return {
        "response_text": summary,
        "messages": [_build_ai_message(summary, followups)],
        "chart_bytes": None,
        "suggested_followups": followups,
    }


# ---------------------------------------------------------------------------
# General analytical question
# ---------------------------------------------------------------------------


async def handle_general(state: AnalyticsState) -> dict:
    last_msg = state["messages"][-1].content if state["messages"] else ""
    prompt = GENERAL_ANALYTICS_PROMPT.format(question=last_msg)
    try:
        resp = await _llm_general.ainvoke([HumanMessage(content=prompt)])
        summary = resp.content
    except Exception:
        summary = (
            "I'm not sure how to analyze that yet. Try asking about a specific metric's trend, "
            "a correlation between two metrics, or your consistency over the last 30 days."
        )

    followups = [
        "Show me trends for my metrics?",
        "What's the top correlation between my metrics?",
        "Give me an overview of all metrics this week?",
    ]
    return {
        "response_text": summary,
        "messages": [_build_ai_message(summary, followups)],
        "chart_bytes": None,
        "suggested_followups": followups,
    }
