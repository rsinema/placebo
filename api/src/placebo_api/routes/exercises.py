from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Query

from placebo_api import db

router = APIRouter(tags=["exercises"])


@router.get("/exercises")
async def list_exercises() -> list[dict]:
    return await db.get_exercises()


@router.get("/exercises/{exercise_id}/sets")
async def get_exercise_sets(
    exercise_id: UUID,
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
) -> list[dict]:
    return await db.get_exercise_sets(exercise_id, start, end)


@router.get("/exercises/{exercise_id}/stats")
async def get_exercise_stats(
    exercise_id: UUID,
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
) -> list[dict]:
    """Per-day aggregates: top weight, total volume, est 1RM (Epley)."""
    return await db.get_exercise_daily_stats(exercise_id, start, end)


@router.get("/workouts/recent")
async def get_recent_workouts(limit: int = Query(20, ge=1, le=200)) -> list[dict]:
    """Recent sets grouped by log_group_id, newest first."""
    return await db.get_recent_workouts(limit)


@router.get("/workouts/summary")
async def get_workout_summary(days: int = Query(7, ge=1, le=365)) -> dict:
    return await db.get_workout_summary(days)


@router.get("/workouts/calendar")
async def get_workout_calendar(days: int = Query(84, ge=1, le=365)) -> list[dict]:
    return await db.get_workout_calendar(days)


@router.get("/workouts/sessions")
async def get_recent_sessions(limit: int = Query(10, ge=1, le=100)) -> list[dict]:
    return await db.get_recent_sessions(limit)
