from datetime import datetime
from uuid import UUID

import asyncpg

_pool: asyncpg.Pool | None = None


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
# Metrics
# ---------------------------------------------------------------------------


async def get_metrics(include_archived: bool = False) -> list[dict]:
    if include_archived:
        rows = await _get_pool().fetch("SELECT * FROM metrics ORDER BY created_at")
    else:
        rows = await _get_pool().fetch(
            "SELECT * FROM metrics WHERE active = TRUE ORDER BY created_at"
        )
    return [dict(row) for row in rows]


async def get_checkin_responses(
    metric_id: UUID,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[dict]:
    query = "SELECT * FROM checkin_responses WHERE metric_id = $1"
    params: list = [metric_id]
    idx = 2

    if start:
        query += f" AND logged_at >= ${idx}"
        params.append(start)
        idx += 1
    if end:
        query += f" AND logged_at <= ${idx}"
        params.append(end)
        idx += 1

    query += " ORDER BY logged_at"
    rows = await _get_pool().fetch(query, *params)
    return [dict(row) for row in rows]


async def get_metric_stats(
    metric_id: UUID,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict:
    """Return avg/min/max/count for a numeric metric over a date range."""
    query = """
        SELECT
            count(*)::int AS count,
            avg(response_value::float) AS avg,
            min(response_value::float) AS min,
            max(response_value::float) AS max
        FROM checkin_responses
        WHERE metric_id = $1
    """
    params: list = [metric_id]
    idx = 2

    if start:
        query += f" AND logged_at >= ${idx}"
        params.append(start)
        idx += 1
    if end:
        query += f" AND logged_at <= ${idx}"
        params.append(end)
        idx += 1

    row = await _get_pool().fetchrow(query, *params)
    return dict(row)


# ---------------------------------------------------------------------------
# Experiments
# ---------------------------------------------------------------------------


async def get_experiments() -> list[dict]:
    rows = await _get_pool().fetch("SELECT * FROM experiments ORDER BY started_at DESC")
    return [dict(row) for row in rows]


async def get_experiment_comparison(experiment_id: UUID) -> dict:
    """Compare metric averages before vs during an experiment."""
    exp = await _get_pool().fetchrow(
        "SELECT * FROM experiments WHERE id = $1", experiment_id
    )
    if not exp:
        return {}

    started_at = exp["started_at"]
    ended_at = exp["ended_at"] or datetime.now(started_at.tzinfo)

    # "Before" = same duration window immediately preceding the experiment
    duration = ended_at - started_at
    before_start = started_at - duration

    before_query = """
        SELECT m.id, m.name,
               avg(cr.response_value::float) AS avg_value
        FROM metrics m
        JOIN checkin_responses cr ON cr.metric_id = m.id
        WHERE cr.logged_at >= $1
          AND cr.logged_at < $2
          AND m.response_type = 'numeric'
        GROUP BY m.id, m.name
    """

    during_query = """
        SELECT m.id, m.name,
               avg(cr.response_value::float) AS avg_value
        FROM metrics m
        JOIN checkin_responses cr ON cr.metric_id = m.id
        WHERE cr.logged_at >= $1
          AND cr.logged_at <= $2
          AND m.response_type = 'numeric'
        GROUP BY m.id, m.name
    """

    before_rows = await _get_pool().fetch(before_query, before_start, started_at)
    during_rows = await _get_pool().fetch(during_query, started_at, ended_at)

    return {
        "experiment": dict(exp),
        "before": [dict(r) for r in before_rows],
        "during": [dict(r) for r in during_rows],
    }


# ---------------------------------------------------------------------------
# Correlations
# ---------------------------------------------------------------------------


async def get_correlation_data(
    metric_a_id: UUID,
    metric_b_id: UUID,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[dict]:
    """Return paired daily values for two metrics (joined by date)."""
    query = """
        SELECT
            a.logged_at::date AS date,
            a.response_value::float AS value_a,
            b.response_value::float AS value_b
        FROM checkin_responses a
        JOIN checkin_responses b
            ON a.logged_at::date = b.logged_at::date
        WHERE a.metric_id = $1
          AND b.metric_id = $2
    """
    params: list = [metric_a_id, metric_b_id]
    idx = 3

    if start:
        query += f" AND a.logged_at >= ${idx}"
        params.append(start)
        idx += 1
    if end:
        query += f" AND a.logged_at <= ${idx}"
        params.append(end)
        idx += 1

    query += " ORDER BY date"
    rows = await _get_pool().fetch(query, *params)
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Check-ins
# ---------------------------------------------------------------------------


async def get_latest_checkin() -> list[dict]:
    """Return the most recent check-in responses (latest logged_at date)."""
    rows = await _get_pool().fetch(
        """
        SELECT cr.*, m.name AS metric_name
        FROM checkin_responses cr
        JOIN metrics m ON m.id = cr.metric_id
        WHERE cr.logged_at::date = (
            SELECT max(logged_at::date) FROM checkin_responses
        )
        ORDER BY cr.logged_at
        """
    )
    return [dict(row) for row in rows]
