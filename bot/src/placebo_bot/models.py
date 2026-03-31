from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class Metric:
    id: UUID
    name: str
    question_prompt: str
    response_type: str  # "numeric", "boolean", "text"
    active: bool
    created_at: datetime
    archived_at: datetime | None = None


@dataclass
class CheckinResponse:
    id: UUID
    metric_id: UUID
    response_value: str
    logged_at: datetime
    notes: str | None = None


@dataclass
class Experiment:
    id: UUID
    name: str
    started_at: datetime
    hypothesis: str | None = None
    ended_at: datetime | None = None
