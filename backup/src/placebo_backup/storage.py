from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterator

import boto3
from botocore.config import Config

from placebo_backup.config import settings


@dataclass
class SnapshotObject:
    key: str
    size: int
    last_modified: datetime
    kind: str  # "daily" | "manual" | "pre-restore" | "other"


def _client():
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        endpoint_url=settings.backup_s3_endpoint_url or None,
        config=Config(retries={"max_attempts": 3, "mode": "standard"}),
    )


def _kind_for(key: str) -> str:
    # Keys look like "<prefix>/<kind>/<timestamp>.dump.gz"
    parts = key.split("/")
    if len(parts) >= 3:
        return parts[-2]
    return "other"


def build_key(kind: str, when: datetime | None = None) -> str:
    when = when or datetime.now(timezone.utc)
    stamp = when.strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"{settings.backup_s3_prefix}/{kind}/{stamp}.dump.gz"


def list_snapshots() -> list[SnapshotObject]:
    s3 = _client()
    paginator = s3.get_paginator("list_objects_v2")
    prefix = f"{settings.backup_s3_prefix}/"
    snapshots: list[SnapshotObject] = []
    for page in paginator.paginate(Bucket=settings.backup_s3_bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key: str = obj["Key"]
            if not key.endswith(".dump.gz"):
                continue
            snapshots.append(
                SnapshotObject(
                    key=key,
                    size=int(obj["Size"]),
                    last_modified=obj["LastModified"],
                    kind=_kind_for(key),
                )
            )
    snapshots.sort(key=lambda s: s.last_modified, reverse=True)
    return snapshots


def upload_stream(key: str, body: Iterator[bytes]) -> None:
    """Upload an in-memory or streamed body to S3 at the given key.

    boto3's upload_fileobj wants a file-like, so we adapt the generator.
    """
    import io

    buf = io.BytesIO()
    for chunk in body:
        buf.write(chunk)
    buf.seek(0)
    _client().upload_fileobj(buf, settings.backup_s3_bucket, key)


def download_to_file(key: str, path: str) -> None:
    _client().download_file(settings.backup_s3_bucket, key, path)


def head(key: str) -> dict | None:
    try:
        return _client().head_object(Bucket=settings.backup_s3_bucket, Key=key)
    except Exception:
        return None


def prune_older_than(days: int) -> list[str]:
    """Delete daily/manual snapshots older than `days`. Pre-restore snapshots
    are kept — they're the safety net we want to err on the side of preserving."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    deleted: list[str] = []
    s3 = _client()
    for snap in list_snapshots():
        if snap.kind == "pre-restore":
            continue
        if snap.last_modified < cutoff:
            s3.delete_object(Bucket=settings.backup_s3_bucket, Key=snap.key)
            deleted.append(snap.key)
    return deleted
