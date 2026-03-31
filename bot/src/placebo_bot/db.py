from uuid import UUID

import asyncpg

from placebo_bot.models import CheckinResponse, Experiment, Metric

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


async def get_active_metrics() -> list[Metric]:
    rows = await _get_pool().fetch(
        "SELECT * FROM metrics WHERE active = TRUE ORDER BY created_at"
    )
    return [Metric(**row) for row in rows]


async def get_metric_by_name(name: str, *, active_only: bool = True) -> Metric | None:
    if active_only:
        row = await _get_pool().fetchrow(
            "SELECT * FROM metrics WHERE lower(name) = lower($1) AND active = TRUE", name
        )
    else:
        row = await _get_pool().fetchrow(
            "SELECT * FROM metrics WHERE lower(name) = lower($1)", name
        )
    return Metric(**row) if row else None


async def create_metric(
    name: str, question_prompt: str, response_type: str = "numeric"
) -> Metric:
    row = await _get_pool().fetchrow(
        """
        INSERT INTO metrics (name, question_prompt, response_type)
        VALUES ($1, $2, $3)
        RETURNING *
        """,
        name,
        question_prompt,
        response_type,
    )
    return Metric(**row)


async def reactivate_metric(
    metric_id: UUID, question_prompt: str, response_type: str
) -> Metric:
    row = await _get_pool().fetchrow(
        """
        UPDATE metrics
        SET active = TRUE, archived_at = NULL,
            question_prompt = $2, response_type = $3
        WHERE id = $1
        RETURNING *
        """,
        metric_id,
        question_prompt,
        response_type,
    )
    return Metric(**row)


async def archive_metric(metric_id: UUID) -> None:
    await _get_pool().execute(
        "UPDATE metrics SET active = FALSE, archived_at = now() WHERE id = $1",
        metric_id,
    )


# ---------------------------------------------------------------------------
# Check-in responses
# ---------------------------------------------------------------------------


async def save_checkin_response(
    metric_id: UUID, response_value: str, notes: str | None = None
) -> CheckinResponse:
    row = await _get_pool().fetchrow(
        """
        INSERT INTO checkin_responses (metric_id, response_value, notes)
        VALUES ($1, $2, $3)
        RETURNING *
        """,
        metric_id,
        response_value,
        notes,
    )
    return CheckinResponse(**row)


# ---------------------------------------------------------------------------
# Experiments
# ---------------------------------------------------------------------------


async def get_active_experiments() -> list[Experiment]:
    rows = await _get_pool().fetch(
        "SELECT * FROM experiments WHERE ended_at IS NULL ORDER BY started_at"
    )
    return [Experiment(**row) for row in rows]


async def create_experiment(name: str, hypothesis: str | None = None) -> Experiment:
    row = await _get_pool().fetchrow(
        """
        INSERT INTO experiments (name, hypothesis)
        VALUES ($1, $2)
        RETURNING *
        """,
        name,
        hypothesis,
    )
    return Experiment(**row)


async def end_experiment(experiment_id: UUID) -> None:
    await _get_pool().execute(
        "UPDATE experiments SET ended_at = now() WHERE id = $1", experiment_id
    )


async def get_all_experiments() -> list[Experiment]:
    rows = await _get_pool().fetch("SELECT * FROM experiments ORDER BY started_at DESC")
    return [Experiment(**row) for row in rows]


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
