from __future__ import annotations

import asyncio
import gzip
import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone

from placebo_backup import storage
from placebo_backup.config import settings

logger = logging.getLogger(__name__)


@dataclass
class BackupResult:
    key: str
    size_bytes: int
    started_at: datetime
    finished_at: datetime
    pruned: list[str] = field(default_factory=list)


@dataclass
class RestoreResult:
    restored_from: str
    pre_restore_key: str | None
    started_at: datetime
    finished_at: datetime


class OperationError(RuntimeError):
    """Raised when pg_dump or pg_restore fails."""


def _pg_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PGHOST"] = settings.postgres_host
    env["PGPORT"] = str(settings.postgres_port)
    env["PGUSER"] = settings.postgres_user
    env["PGPASSWORD"] = settings.postgres_password
    env["PGDATABASE"] = settings.postgres_db
    return env


async def _run(cmd: list[str], *, stdin: bytes | None = None, env: dict | None = None) -> tuple[bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE if stdin is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await proc.communicate(input=stdin)
    if proc.returncode != 0:
        raise OperationError(
            f"command {' '.join(cmd)} failed (exit {proc.returncode}): {stderr.decode(errors='replace')}"
        )
    return stdout, stderr


async def run_backup(kind: str = "manual") -> BackupResult:
    """Dump the placebo DB, gzip it, upload to S3, prune old snapshots."""
    started_at = datetime.now(timezone.utc)
    key = storage.build_key(kind, started_at)

    logger.info("starting %s backup -> s3://%s/%s", kind, settings.backup_s3_bucket, key)

    # pg_dump custom format (-Fc) is binary, smaller than plain SQL, and lets
    # pg_restore handle --clean cleanly. We gzip on top because text-ish indices
    # still compress nicely and S3 storage is per-byte.
    pg_dump_cmd = ["pg_dump", "-Fc", "--no-owner", "--no-privileges"]
    dump_bytes, _ = await _run(pg_dump_cmd, env=_pg_env())
    gzipped = gzip.compress(dump_bytes, compresslevel=6)

    # Upload in a thread — boto3 is sync.
    await asyncio.to_thread(storage.upload_stream, key, iter([gzipped]))

    pruned = await asyncio.to_thread(storage.prune_older_than, settings.backup_retention_days)

    finished_at = datetime.now(timezone.utc)
    logger.info(
        "backup complete: %s (%d bytes, pruned %d old snapshots)",
        key,
        len(gzipped),
        len(pruned),
    )
    return BackupResult(
        key=key,
        size_bytes=len(gzipped),
        started_at=started_at,
        finished_at=finished_at,
        pruned=pruned,
    )


async def run_restore(key: str) -> RestoreResult:
    """Restore the DB from an S3 snapshot.

    Steps:
      1. Optionally take a pre-restore safety snapshot
      2. Download the target snapshot
      3. Terminate other connections to the DB
      4. Drop and recreate the public schema (wipes everything)
      5. pg_restore from the dump
    """
    started_at = datetime.now(timezone.utc)

    head = await asyncio.to_thread(storage.head, key)
    if head is None:
        raise OperationError(f"snapshot not found: {key}")

    pre_restore_key: str | None = None
    if settings.backup_pre_restore_snapshot:
        logger.info("taking pre-restore safety snapshot")
        pre = await run_backup(kind="pre-restore")
        pre_restore_key = pre.key

    logger.info("downloading snapshot %s", key)
    with tempfile.NamedTemporaryFile(suffix=".dump.gz", delete=False) as gz_file:
        gz_path = gz_file.name
    try:
        await asyncio.to_thread(storage.download_to_file, key, gz_path)

        dump_path = gz_path[:-3]  # strip .gz
        with gzip.open(gz_path, "rb") as src, open(dump_path, "wb") as dst:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)

        try:
            await _wipe_schema()
            logger.info("running pg_restore from %s", dump_path)
            await _run(
                [
                    "pg_restore",
                    "--no-owner",
                    "--no-privileges",
                    "--dbname",
                    settings.postgres_db,
                    dump_path,
                ],
                env=_pg_env(),
            )
        finally:
            try:
                os.unlink(dump_path)
            except FileNotFoundError:
                pass
    finally:
        try:
            os.unlink(gz_path)
        except FileNotFoundError:
            pass

    finished_at = datetime.now(timezone.utc)
    logger.info("restore complete from %s", key)
    return RestoreResult(
        restored_from=key,
        pre_restore_key=pre_restore_key,
        started_at=started_at,
        finished_at=finished_at,
    )


async def _wipe_schema() -> None:
    """Terminate other connections and drop+recreate the public schema."""
    sql = f"""
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = current_database()
          AND pid <> pg_backend_pid();
        DROP SCHEMA IF EXISTS public CASCADE;
        CREATE SCHEMA public;
        GRANT ALL ON SCHEMA public TO {settings.postgres_user};
        GRANT ALL ON SCHEMA public TO public;
    """
    logger.info("wiping public schema before restore")
    await _run(["psql", "-v", "ON_ERROR_STOP=1", "-c", sql], env=_pg_env())
