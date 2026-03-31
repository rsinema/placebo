from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Query

from placebo_api import db

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("")
async def list_metrics(include_archived: bool = False) -> list[dict]:
    return await db.get_metrics(include_archived)


@router.get("/{metric_id}/responses")
async def get_responses(
    metric_id: UUID,
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
) -> list[dict]:
    return await db.get_checkin_responses(metric_id, start, end)


@router.get("/{metric_id}/stats")
async def get_stats(
    metric_id: UUID,
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
) -> dict:
    return await db.get_metric_stats(metric_id, start, end)


@router.get("/correlation")
async def get_correlation(
    metric_a: UUID = Query(...),
    metric_b: UUID = Query(...),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
) -> list[dict]:
    return await db.get_correlation_data(metric_a, metric_b, start, end)
