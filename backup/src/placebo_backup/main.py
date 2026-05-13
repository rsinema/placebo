from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from placebo_backup import storage
from placebo_backup.operations import OperationError, run_backup, run_restore
from placebo_backup.scheduler import daily_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("placebo_backup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(daily_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Placebo Backup", version="0.1.0", lifespan=lifespan)

# Serialize backup/restore operations — running two pg_dumps or, worse, a backup
# while a restore is wiping the schema would be Very Bad.
_op_lock = asyncio.Lock()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/backups")
async def list_backups() -> list[dict]:
    snaps = await asyncio.to_thread(storage.list_snapshots)
    return [
        {
            "key": s.key,
            "size_bytes": s.size,
            "last_modified": s.last_modified.isoformat(),
            "kind": s.kind,
        }
        for s in snaps
    ]


@app.post("/backups")
async def create_backup() -> dict:
    if _op_lock.locked():
        raise HTTPException(status_code=409, detail="another backup or restore is in progress")
    async with _op_lock:
        try:
            result = await run_backup(kind="manual")
        except OperationError as e:
            raise HTTPException(status_code=500, detail=str(e))
    return {
        "key": result.key,
        "size_bytes": result.size_bytes,
        "started_at": result.started_at.isoformat(),
        "finished_at": result.finished_at.isoformat(),
        "pruned": result.pruned,
    }


@app.post("/backups/{key:path}/restore")
async def restore_backup(key: str) -> dict:
    if _op_lock.locked():
        raise HTTPException(status_code=409, detail="another backup or restore is in progress")
    async with _op_lock:
        try:
            result = await run_restore(key)
        except OperationError as e:
            raise HTTPException(status_code=500, detail=str(e))
    return {
        "restored_from": result.restored_from,
        "pre_restore_key": result.pre_restore_key,
        "started_at": result.started_at.isoformat(),
        "finished_at": result.finished_at.isoformat(),
    }
