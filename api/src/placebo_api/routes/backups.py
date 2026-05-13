from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException

from placebo_api.config import settings

router = APIRouter(prefix="/backups", tags=["backups"])

# pg_dump/pg_restore can take a while on a moderately-sized DB; the timeout
# guards against the backup service hanging, not against a slow but valid op.
_BACKUP_TIMEOUT_S = 600.0


async def _proxy(method: str, path: str) -> dict | list:
    url = f"{settings.backup_service_url}{path}"
    try:
        async with httpx.AsyncClient(timeout=_BACKUP_TIMEOUT_S) as client:
            resp = await client.request(method, url)
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"backup service unreachable: {e}")
    if resp.status_code >= 400:
        # Surface the backup service's error body directly so the dashboard
        # can show something useful.
        detail = resp.json().get("detail") if resp.headers.get("content-type", "").startswith("application/json") else resp.text
        raise HTTPException(status_code=resp.status_code, detail=detail)
    return resp.json()


@router.get("")
async def list_backups() -> list[dict]:
    return await _proxy("GET", "/backups")


@router.post("")
async def create_backup() -> dict:
    return await _proxy("POST", "/backups")


@router.post("/restore")
async def restore_backup(key: str) -> dict:
    # The S3 key has slashes in it; pass through as a query param to keep
    # routing unambiguous on this side.
    return await _proxy("POST", f"/backups/{quote(key, safe='')}/restore")
