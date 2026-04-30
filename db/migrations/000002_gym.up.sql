CREATE TABLE IF NOT EXISTS exercises (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL UNIQUE,
    category    TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS exercise_sets (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    exercise_id   UUID NOT NULL REFERENCES exercises(id),
    set_number    INT NOT NULL,
    reps          INT NOT NULL,
    weight        NUMERIC(6,2),
    rpe           NUMERIC(3,1),
    notes         TEXT,
    log_group_id  UUID NOT NULL,
    logged_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_exercise_sets_exercise_logged
    ON exercise_sets(exercise_id, logged_at);

CREATE INDEX IF NOT EXISTS idx_exercise_sets_log_group
    ON exercise_sets(log_group_id);
