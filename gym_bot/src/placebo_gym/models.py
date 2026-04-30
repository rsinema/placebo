from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass
class Exercise:
    id: UUID
    name: str
    created_at: datetime
    category: str | None = None


@dataclass
class ExerciseSet:
    id: UUID
    exercise_id: UUID
    set_number: int
    reps: int
    log_group_id: UUID
    logged_at: datetime
    weight: Decimal | None = None
    rpe: Decimal | None = None
    notes: str | None = None
