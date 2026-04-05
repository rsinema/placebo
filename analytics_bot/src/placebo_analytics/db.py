import logging
from datetime import datetime, timezone
from uuid import UUID

import asyncpg

from placebo_analytics.models import Experiment, Metric

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None

# ---------------------------------------------------------------------------
# Pool management
# ---------------------------------------------------------------------------


async def init_pool(database_url: str) -> asyncpg.Pool:
    global _pool
    _pool = await asyncpg.create_pool(database_url)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def _get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool not initialized")
    return _pool


# ---------------------------------------------------------------------------
# Bot settings
# ---------------------------------------------------------------------------


async def get_bot_setting(key: str) -> str | None:
    row = await _get_pool().fetchrow(
        "SELECT value FROM bot_settings WHERE key = $1", key
    )
    return row["value"] if row else None


async def set_bot_setting(key: str, value: str) -> None:
    await _get_pool().execute(
        """
        INSERT INTO bot_settings (key, value)
        VALUES ($1, $2)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """,
        key,
        value,
    )


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


async def get_active_metrics() -> list[Metric]:
    rows = await _get_pool().fetch(
        "SELECT * FROM metrics WHERE active = TRUE ORDER BY created_at"
    )
    return [Metric(**row) for row in rows]


async def get_all_metrics() -> list[Metric]:
    rows = await _get_pool().fetch("SELECT * FROM metrics ORDER BY created_at")
    return [Metric(**row) for row in rows]


async def get_metric_by_name(name: str) -> Metric | None:
    row = await _get_pool().fetchrow(
        "SELECT * FROM metrics WHERE lower(name) = lower($1) AND active = TRUE", name
    )
    return Metric(**row) if row else None


# ---------------------------------------------------------------------------
# Check-in responses — analytical queries
# ---------------------------------------------------------------------------


async def get_rolling_avg(metric_id: UUID, days: int = 30) -> list[dict]:
    """Return daily averages for a metric over the last N days."""
    rows = await _get_pool().fetch(
        """
        SELECT
            logged_at::date AS date,
            avg(response_value::float) AS avg_value
        FROM checkin_responses
        WHERE metric_id = $1
          AND logged_at >= NOW() - INTERVAL '1 day' * $2
          AND response_value ~ '^-?[0-9]+\\.?[0-9]*$'
        GROUP BY date
        ORDER BY date
        """,
        metric_id,
        days,
    )
    return [dict(row) for row in rows]


async def get_trend_points(metric_id: UUID, limit: int = 30) -> list[dict]:
    """Return (days_since_epoch, value) pairs for slope computation."""
    rows = await _get_pool().fetch(
        """
        SELECT
            (logged_at::date - date '1970-01-01') AS days_since_epoch,
            response_value::float AS value
        FROM checkin_responses
        WHERE metric_id = $1
          AND response_value ~ '^-?[0-9]+\\.?[0-9]*$'
        ORDER BY logged_at DESC
        LIMIT $2
        """,
        metric_id,
        limit,
    )
    return [dict(row) for row in rows]


async def get_metric_stats(metric_id: UUID, days: int = 30) -> dict | None:
    """Return summary stats for a metric over a period."""
    row = await _get_pool().fetchrow(
        """
        SELECT
            avg(response_value::float) AS avg_value,
            min(response_value::float) AS min_value,
            max(response_value::float) AS max_value,
            stddev(response_value::float) AS stddev_value,
            count(*) AS count
        FROM checkin_responses
        WHERE metric_id = $1
          AND logged_at >= NOW() - INTERVAL '1 day' * $2
          AND response_value ~ '^-?[0-9]+\\.?[0-9]*$'
        """,
        metric_id,
        days,
    )
    return dict(row) if row else None


async def get_consistency(metric_id: UUID, days: int = 30) -> dict:
    """Return consistency / streak data for a metric."""
    rows = await _get_pool().fetch(
        """
        SELECT logged_at::date AS date
        FROM checkin_responses
        WHERE metric_id = $1
          AND logged_at >= NOW() - INTERVAL '1 day' * $2
        GROUP BY date
        ORDER BY date
        """,
        metric_id,
        days,
    )
    dates = [row["date"] for row in rows]

    if not dates:
        return {"days_with_data": 0, "total_days": days, "consistency_pct": 0.0, "longest_streak": 0}

    # Consistency percentage
    consistency_pct = len(dates) / days * 100

    # Longest consecutive streak
    longest = 1
    current = 1
    for i in range(1, len(dates)):
        if (dates[i] - dates[i - 1]).days == 1:
            current += 1
            longest = max(longest, current)
        else:
            current = 1

    return {
        "days_with_data": len(dates),
        "total_days": days,
        "consistency_pct": round(consistency_pct, 1),
        "longest_streak": longest,
    }


async def get_weekly_aggregation(metric_id: UUID, weeks: int = 4) -> list[dict]:
    """Return weekly averages for a metric."""
    rows = await _get_pool().fetch(
        """
        SELECT
            date_trunc('week', logged_at)::date AS week_start,
            avg(response_value::float) AS avg_value,
            count(*) AS count
        FROM checkin_responses
        WHERE metric_id = $1
          AND logged_at >= NOW() - INTERVAL '1 week' * $2
          AND response_value ~ '^-?[0-9]+\\.?[0-9]*$'
        GROUP BY week_start
        ORDER BY week_start
        """,
        metric_id,
        weeks,
    )
    return [dict(row) for row in rows]


async def get_multi_metric_summary(metric_ids: list[UUID], days: int = 7) -> list[dict]:
    """Return summary stats for multiple metrics in a single query."""
    rows = await _get_pool().fetch(
        """
        SELECT
            m.id,
            m.name,
            m.question_prompt,
            m.response_type,
            s.avg_value,
            s.min_value,
            s.max_value,
            s.count
        FROM metrics m
        LEFT JOIN (
            SELECT
                metric_id,
                avg(response_value::float) AS avg_value,
                min(response_value::float) AS min_value,
                max(response_value::float) AS max_value,
                count(*) AS count
            FROM checkin_responses
            WHERE logged_at >= NOW() - INTERVAL '1 day' * $2
              AND response_value ~ '^-?[0-9]+\\.?[0-9]*$'
            GROUP BY metric_id
        ) s ON s.metric_id = m.id
        WHERE m.id = ANY($1::uuid[])
          AND m.active = TRUE
        ORDER BY m.created_at
        """,
        metric_ids,
        days,
    )
    return [dict(row) for row in rows]


async def get_all_numeric_metric_pairs(days: int = 30) -> list[dict]:
    """Return all numeric metric pairs with enough data for correlation."""
    rows = await _get_pool().fetch(
        """
        SELECT
            a.metric_id AS metric_a_id,
            a.name AS metric_a_name,
            b.metric_id AS metric_b_id,
            b.name AS metric_b_name,
            a.avg_value AS value_a,
            b.avg_value AS value_b,
            a.date_val AS date_val
        FROM (
            SELECT
                cr.metric_id,
                m.name,
                cr.response_value::float AS avg_value,
                cr.logged_at::date AS date_val
            FROM checkin_responses cr
            JOIN metrics m ON m.id = cr.metric_id
            WHERE cr.logged_at >= NOW() - INTERVAL '1 day' * $1
              AND cr.response_value ~ '^-?[0-9]+\\.?[0-9]*$'
        ) a
        JOIN (
            SELECT
                cr.metric_id,
                m.name,
                cr.response_value::float AS avg_value,
                cr.logged_at::date AS date_val
            FROM checkin_responses cr
            JOIN metrics m ON m.id = cr.metric_id
            WHERE cr.logged_at >= NOW() - INTERVAL '1 day' * $1
              AND cr.response_value ~ '^-?[0-9]+\\.?[0-9]*$'
        ) b ON a.date_val = b.date_val AND a.metric_id < b.metric_id
        ORDER BY a.metric_id, b.metric_id
        """,
        days,
    )
    return [dict(row) for row in rows]


async def get_correlation_pairs(metric_a_id: UUID, metric_b_id: UUID, days: int = 30) -> list[dict]:
    """Return paired data points for two metrics for scatter plot."""
    rows = await _get_pool().fetch(
        """
        SELECT
            a.date_val AS date_val,
            a.avg_value AS value_a,
            b.avg_value AS value_b
        FROM (
            SELECT
                cr.metric_id,
                cr.response_value::float AS avg_value,
                cr.logged_at::date AS date_val
            FROM checkin_responses cr
            WHERE cr.metric_id = $1
              AND cr.logged_at >= NOW() - INTERVAL '1 day' * $3
              AND cr.response_value ~ '^-?[0-9]+\\.?[0-9]*$'
        ) a
        JOIN (
            SELECT
                cr.metric_id,
                cr.response_value::float AS avg_value,
                cr.logged_at::date AS date_val
            FROM checkin_responses cr
            WHERE cr.metric_id = $2
              AND cr.logged_at >= NOW() - INTERVAL '1 day' * $3
              AND cr.response_value ~ '^-?[0-9]+\\.?[0-9]*$'
        ) b ON a.date_val = b.date_val
        ORDER BY a.date_val
        """,
        metric_a_id,
        metric_b_id,
        days,
    )
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Period comparison
# ---------------------------------------------------------------------------


async def get_period_comparison(metric_id: UUID, days: int = 7) -> dict:
    """Return this week vs. last week stats for a metric."""
    rows = await _get_pool().fetch(
        """
        WITH periods AS (
            SELECT
                CASE
                    WHEN logged_at >= NOW() - INTERVAL '1 day' * $2 THEN 'this_week'
                    WHEN logged_at >= NOW() - INTERVAL '1 day' * ($2 * 2) THEN 'last_week'
                END AS period,
                response_value::float AS value
            FROM checkin_responses
            WHERE metric_id = $1
              AND logged_at >= NOW() - INTERVAL '1 day' * ($2 * 2)
              AND response_value ~ '^-?[0-9]+\\.?[0-9]*$'
        )
        SELECT
            period,
            avg(value) AS avg_value,
            min(value) AS min_value,
            max(value) AS max_value,
            count(*) AS count
        FROM periods
        WHERE period IS NOT NULL
        GROUP BY period
        ORDER BY period
        """,
        metric_id,
        days,
    )
    result = {}
    for row in rows:
        result[row["period"]] = dict(row)
    return result


# ---------------------------------------------------------------------------
# Experiment analysis
# ---------------------------------------------------------------------------


async def get_experiment_data(experiment_id: UUID) -> dict | None:
    row = await _get_pool().fetchrow(
        "SELECT * FROM experiments WHERE id = $1", experiment_id
    )
    return dict(row) if row else None


async def get_active_experiments() -> list[Experiment]:
    rows = await _get_pool().fetch(
        "SELECT * FROM experiments WHERE ended_at IS NULL ORDER BY started_at"
    )
    return [Experiment(**row) for row in rows]


async def get_experiment_comparison(metric_id: UUID, experiment_id: UUID) -> dict:
    """Return before vs. during experiment comparison for a metric."""
    exp = await get_experiment_data(experiment_id)
    if not exp:
        return {}

    start = exp["started_at"]
    ended = exp.get("ended_at") or datetime.now(timezone.utc)
    duration = max((ended - start).days, 1)

    rows = await _get_pool().fetch(
        """
        WITH periods AS (
            SELECT
                CASE
                    WHEN logged_at < $2 THEN 'before'
                    WHEN logged_at >= $2 THEN 'during'
                END AS period,
                response_value::float AS value
            FROM checkin_responses
            WHERE metric_id = $1
              AND logged_at >= $2 - (INTERVAL '1 day' * $3)
              AND logged_at <= $2 + (INTERVAL '1 day' * $3)
              AND response_value ~ '^-?[0-9]+\\.?[0-9]*$'
        )
        SELECT
            period,
            avg(value) AS avg_value,
            min(value) AS min_value,
            max(value) AS max_value,
            stddev(value) AS stddev_value,
            count(*) AS count
        FROM periods
        WHERE period IS NOT NULL
        GROUP BY period
        ORDER BY period
        """,
        metric_id,
        start,
        duration,
    )
    result = {}
    for row in rows:
        result[row["period"]] = dict(row)
    return result


async def get_experiment_metric_comparisons(experiment_id: UUID) -> list[dict]:
    """Return before/during comparisons for all metrics in an experiment window."""
    exp = await get_experiment_data(experiment_id)
    if not exp:
        return []

    start = exp["started_at"]
    ended = exp.get("ended_at") or datetime.now(timezone.utc)
    duration = max((ended - start).days, 1)

    rows = await _get_pool().fetch(
        """
        WITH periods AS (
            SELECT
                cr.metric_id,
                m.name AS metric_name,
                CASE
                    WHEN cr.logged_at < $1 THEN 'before'
                    WHEN cr.logged_at >= $1 THEN 'during'
                END AS period,
                cr.response_value::float AS value
            FROM checkin_responses cr
            JOIN metrics m ON m.id = cr.metric_id
            WHERE cr.logged_at >= $1 - (INTERVAL '1 day' * $2)
              AND cr.logged_at <= $1 + (INTERVAL '1 day' * $2)
              AND cr.response_value ~ '^-?[0-9]+\\.?[0-9]*$'
        )
        SELECT
            metric_id,
            metric_name,
            period,
            avg(value) AS avg_value,
            count(*) AS count
        FROM periods
        WHERE period IS NOT NULL
        GROUP BY metric_id, metric_name, period
        ORDER BY metric_id, period
        """,
        start,
        duration,
    )
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Boolean metric frequency
# ---------------------------------------------------------------------------


async def get_boolean_frequency(metric_id: UUID, days: int = 30) -> dict | None:
    """Return true/false frequency for a boolean metric."""
    row = await _get_pool().fetchrow(
        """
        SELECT
            sum(CASE WHEN response_value IN ('true', '1', 'yes') THEN 1 ELSE 0 END) AS true_count,
            sum(CASE WHEN response_value IN ('false', '0', 'no') THEN 1 ELSE 0 END) AS false_count,
            count(*) AS total
        FROM checkin_responses
        WHERE metric_id = $1
          AND logged_at >= NOW() - INTERVAL '1 day' * $2
          AND response_value IN ('true', 'false', '1', '0', 'yes', 'no')
        """,
        metric_id,
        days,
    )
    return dict(row) if row else None
