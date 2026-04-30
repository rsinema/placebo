from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

import asyncpg

from placebo_gym.models import Exercise, ExerciseSet

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
# Exercises
# ---------------------------------------------------------------------------


async def get_exercise_by_name(name: str) -> Exercise | None:
    row = await _get_pool().fetchrow(
        "SELECT * FROM exercises WHERE lower(name) = lower($1)", name
    )
    return Exercise(**row) if row else None


async def get_all_exercises() -> list[Exercise]:
    rows = await _get_pool().fetch("SELECT * FROM exercises ORDER BY name")
    return [Exercise(**row) for row in rows]


async def upsert_exercise(name: str, category: str | None = None) -> Exercise:
    """Return existing exercise (case-insensitive) or create a new one."""
    existing = await get_exercise_by_name(name)
    if existing:
        return existing
    row = await _get_pool().fetchrow(
        """
        INSERT INTO exercises (name, category)
        VALUES ($1, $2)
        RETURNING *
        """,
        name,
        category,
    )
    return Exercise(**row)


# ---------------------------------------------------------------------------
# Exercise sets
# ---------------------------------------------------------------------------


async def save_exercise_sets(
    exercise_id: UUID,
    sets: list[dict],
    notes: str | None = None,
) -> tuple[UUID, list[ExerciseSet]]:
    """Insert all sets under one log_group_id. `sets` items have keys reps, weight, rpe."""
    log_group_id = uuid4()
    saved: list[ExerciseSet] = []
    pool = _get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            for idx, s in enumerate(sets, start=1):
                weight = s.get("weight")
                row = await conn.fetchrow(
                    """
                    INSERT INTO exercise_sets
                        (exercise_id, set_number, reps, weight, rpe, notes, log_group_id)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    RETURNING *
                    """,
                    exercise_id,
                    idx,
                    int(s["reps"]),
                    Decimal(str(weight)) if weight is not None else None,
                    Decimal(str(s["rpe"])) if s.get("rpe") is not None else None,
                    notes,
                    log_group_id,
                )
                saved.append(ExerciseSet(**row))
    return log_group_id, saved


async def get_last_log_group(chat_id: int | None = None) -> UUID | None:
    """Return the most recent log_group_id, or None if no sets logged."""
    # chat_id reserved for future per-user filtering; single-user for now.
    row = await _get_pool().fetchrow(
        """
        SELECT log_group_id
        FROM exercise_sets
        ORDER BY logged_at DESC
        LIMIT 1
        """
    )
    return row["log_group_id"] if row else None


async def delete_log_group(log_group_id: UUID) -> int:
    """Delete all sets in a log group. Returns count deleted."""
    result = await _get_pool().execute(
        "DELETE FROM exercise_sets WHERE log_group_id = $1", log_group_id
    )
    # asyncpg returns "DELETE n"
    try:
        return int(result.split()[-1])
    except (ValueError, IndexError):
        return 0


async def get_log_group_sets(log_group_id: UUID) -> list[ExerciseSet]:
    rows = await _get_pool().fetch(
        "SELECT * FROM exercise_sets WHERE log_group_id = $1 ORDER BY set_number",
        log_group_id,
    )
    return [ExerciseSet(**row) for row in rows]


async def get_recent_sets(limit: int = 20) -> list[dict]:
    """Return recent sets joined with exercise name, newest first."""
    rows = await _get_pool().fetch(
        """
        SELECT es.*, e.name AS exercise_name
        FROM exercise_sets es
        JOIN exercises e ON e.id = es.exercise_id
        ORDER BY es.logged_at DESC
        LIMIT $1
        """,
        limit,
    )
    return [dict(row) for row in rows]


async def get_sets_for_exercise(
    exercise_id: UUID,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[ExerciseSet]:
    query = "SELECT * FROM exercise_sets WHERE exercise_id = $1"
    params: list = [exercise_id]
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
    return [ExerciseSet(**row) for row in rows]
