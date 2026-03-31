from fastapi import APIRouter

from placebo_api import db

router = APIRouter(prefix="/checkins", tags=["checkins"])


@router.get("/latest")
async def get_latest() -> list[dict]:
    return await db.get_latest_checkin()
