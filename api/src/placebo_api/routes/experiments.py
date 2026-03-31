from uuid import UUID

from fastapi import APIRouter

from placebo_api import db

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.get("")
async def list_experiments() -> list[dict]:
    return await db.get_experiments()


@router.get("/{experiment_id}/comparison")
async def get_comparison(experiment_id: UUID) -> dict:
    return await db.get_experiment_comparison(experiment_id)
