from datetime import datetime, timedelta
from uuid import UUID

import asyncpg

_pool: asyncpg.Pool | None = None


def _inclusive_end(end: datetime) -> datetime:
    """Bump a midnight end-date forward one day so range comparisons with
    `< end` include the full final day. If the caller passed a precise time,
    leave it alone."""
    if end.hour == 0 and end.minute == 0 and end.second == 0 and end.microsecond == 0:
        return end + timedelta(days=1)
    return end


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
        query += f" AND logged_at < ${idx}"
        params.append(_inclusive_end(end))
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
        query += f" AND logged_at < ${idx}"
        params.append(_inclusive_end(end))
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
        query += f" AND a.logged_at < ${idx}"
        params.append(_inclusive_end(end))
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


# ---------------------------------------------------------------------------
# Exercises
# ---------------------------------------------------------------------------


async def get_exercises() -> list[dict]:
    rows = await _get_pool().fetch(
        """
        SELECT e.*,
               (SELECT count(*) FROM exercise_sets es WHERE es.exercise_id = e.id) AS set_count,
               (SELECT max(logged_at) FROM exercise_sets es WHERE es.exercise_id = e.id) AS last_logged_at
        FROM exercises e
        ORDER BY e.name
        """
    )
    return [dict(row) for row in rows]


async def get_exercise_sets(
    exercise_id: UUID,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[dict]:
    query = "SELECT * FROM exercise_sets WHERE exercise_id = $1"
    params: list = [exercise_id]
    idx = 2
    if start:
        query += f" AND logged_at >= ${idx}"
        params.append(start)
        idx += 1
    if end:
        query += f" AND logged_at < ${idx}"
        params.append(_inclusive_end(end))
        idx += 1
    query += " ORDER BY logged_at, set_number"
    rows = await _get_pool().fetch(query, *params)
    return [dict(row) for row in rows]


async def get_exercise_daily_stats(
    exercise_id: UUID,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[dict]:
    """Per-day top weight, total volume, and estimated 1RM (Epley).

    Estimated 1RM is computed per-set as weight * (1 + reps/30), then we take
    the max across sets that day.
    """
    query = """
        SELECT
            logged_at::date AS date,
            max(weight)::float AS top_weight,
            sum(reps * weight)::float AS volume,
            max(weight * (1 + reps / 30.0))::float AS est_1rm,
            count(*)::int AS set_count
        FROM exercise_sets
        WHERE exercise_id = $1
          AND weight IS NOT NULL
    """
    params: list = [exercise_id]
    idx = 2
    if start:
        query += f" AND logged_at >= ${idx}"
        params.append(start)
        idx += 1
    if end:
        query += f" AND logged_at < ${idx}"
        params.append(_inclusive_end(end))
        idx += 1
    query += " GROUP BY logged_at::date ORDER BY logged_at::date"
    rows = await _get_pool().fetch(query, *params)
    return [dict(row) for row in rows]


async def get_recent_workouts(limit: int = 20) -> list[dict]:
    """Return recent sets grouped by log_group_id, newest first.

    Each result is one log group with: id, exercise_id, exercise_name,
    logged_at (earliest in group), and a list of sets.
    """
    # Pick the N newest log groups, then fetch their sets.
    group_rows = await _get_pool().fetch(
        """
        SELECT log_group_id, exercise_id, min(logged_at) AS logged_at
        FROM exercise_sets
        GROUP BY log_group_id, exercise_id
        ORDER BY logged_at DESC
        LIMIT $1
        """,
        limit,
    )
    if not group_rows:
        return []

    group_ids = [r["log_group_id"] for r in group_rows]
    set_rows = await _get_pool().fetch(
        """
        SELECT es.*, e.name AS exercise_name
        FROM exercise_sets es
        JOIN exercises e ON e.id = es.exercise_id
        WHERE es.log_group_id = ANY($1::uuid[])
        ORDER BY es.logged_at, es.set_number
        """,
        group_ids,
    )

    by_group: dict = {gid: [] for gid in group_ids}
    for row in set_rows:
        by_group[row["log_group_id"]].append(
            {
                "id": str(row["id"]),
                "set_number": row["set_number"],
                "reps": row["reps"],
                "weight": float(row["weight"]) if row["weight"] is not None else None,
                "rpe": float(row["rpe"]) if row["rpe"] is not None else None,
                "notes": row["notes"],
            }
        )

    workouts = []
    name_by_group = {row["log_group_id"]: None for row in set_rows}
    for row in set_rows:
        name_by_group[row["log_group_id"]] = row["exercise_name"]

    for r in group_rows:
        gid = r["log_group_id"]
        workouts.append(
            {
                "log_group_id": str(gid),
                "exercise_id": str(r["exercise_id"]),
                "exercise_name": name_by_group.get(gid),
                "logged_at": r["logged_at"].isoformat(),
                "sets": by_group[gid],
            }
        )
    return workouts


async def get_workout_summary(days: int = 7) -> dict:
    """Aggregate metrics across the last N days."""
    interval = f"{int(days)} days"
    totals = await _get_pool().fetchrow(
        f"""
        SELECT
            count(*)::int AS set_count,
            count(DISTINCT log_group_id)::int AS lift_count,
            count(DISTINCT logged_at::date)::int AS session_count
        FROM exercise_sets
        WHERE logged_at >= now() - INTERVAL '{interval}'
        """
    )
    top_exercises = await _get_pool().fetch(
        f"""
        SELECT
            e.id,
            e.name,
            max(es.weight)::float AS top_weight,
            count(DISTINCT es.log_group_id)::int AS lift_count,
            count(*)::int AS set_count
        FROM exercise_sets es
        JOIN exercises e ON e.id = es.exercise_id
        WHERE es.logged_at >= now() - INTERVAL '{interval}'
        GROUP BY e.id, e.name
        ORDER BY set_count DESC, lift_count DESC
        LIMIT 5
        """
    )
    return {
        "days": days,
        "set_count": totals["set_count"],
        "lift_count": totals["lift_count"],
        "session_count": totals["session_count"],
        "top_exercises": [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "top_weight": r["top_weight"],
                "lift_count": r["lift_count"],
                "set_count": r["set_count"],
            }
            for r in top_exercises
        ],
    }


async def get_workout_calendar(days: int = 84) -> list[dict]:
    """Per-day set count and volume for a heatmap."""
    interval = f"{int(days)} days"
    rows = await _get_pool().fetch(
        f"""
        SELECT
            logged_at::date AS date,
            count(*)::int AS set_count,
            coalesce(sum(reps * weight), 0)::float AS volume
        FROM exercise_sets
        WHERE logged_at >= now() - INTERVAL '{interval}'
        GROUP BY logged_at::date
        ORDER BY logged_at::date
        """
    )
    return [
        {
            "date": r["date"].isoformat(),
            "set_count": r["set_count"],
            "volume": r["volume"],
        }
        for r in rows
    ]


async def get_recent_sessions(limit: int = 10) -> list[dict]:
    """Recent training days, with all exercises per day grouped together."""
    date_rows = await _get_pool().fetch(
        """
        SELECT DISTINCT logged_at::date AS date
        FROM exercise_sets
        ORDER BY date DESC
        LIMIT $1
        """,
        limit,
    )
    if not date_rows:
        return []

    dates = [r["date"] for r in date_rows]
    set_rows = await _get_pool().fetch(
        """
        SELECT es.*, e.name AS exercise_name, es.logged_at::date AS date
        FROM exercise_sets es
        JOIN exercises e ON e.id = es.exercise_id
        WHERE es.logged_at::date = ANY($1::date[])
        ORDER BY es.logged_at, es.set_number
        """,
        dates,
    )

    sessions: dict[str, dict] = {}
    for row in set_rows:
        date = row["date"].isoformat()
        if date not in sessions:
            sessions[date] = {
                "date": date,
                "started_at": row["logged_at"].isoformat(),
                "exercises": {},
            }
        gid = str(row["log_group_id"])
        if gid not in sessions[date]["exercises"]:
            sessions[date]["exercises"][gid] = {
                "log_group_id": gid,
                "exercise_id": str(row["exercise_id"]),
                "exercise_name": row["exercise_name"],
                "sets": [],
            }
        sessions[date]["exercises"][gid]["sets"].append(
            {
                "set_number": row["set_number"],
                "reps": row["reps"],
                "weight": float(row["weight"]) if row["weight"] is not None else None,
            }
        )

    result = []
    for date in sorted(sessions.keys(), reverse=True):
        s = sessions[date]
        s["exercises"] = list(s["exercises"].values())
        s["set_count"] = sum(len(e["sets"]) for e in s["exercises"])
        s["volume"] = sum(
            (set_["weight"] or 0) * set_["reps"]
            for e in s["exercises"]
            for set_ in e["sets"]
        )
        result.append(s)
    return result
