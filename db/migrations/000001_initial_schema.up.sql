CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$ BEGIN
    CREATE TYPE response_type_enum AS ENUM ('numeric', 'boolean', 'text');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS metrics (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL UNIQUE,
    question_prompt TEXT NOT NULL,
    response_type   response_type_enum NOT NULL DEFAULT 'numeric',
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    archived_at     TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS checkin_responses (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    metric_id       UUID NOT NULL REFERENCES metrics(id),
    response_value  TEXT NOT NULL,
    notes           TEXT,
    logged_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_checkin_responses_metric_logged
    ON checkin_responses(metric_id, logged_at);

CREATE TABLE IF NOT EXISTS experiments (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    hypothesis  TEXT,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS bot_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT INTO metrics (name, question_prompt, response_type) VALUES
    ('sleep_quality',   'How would you rate your sleep quality? (1-10)',        'numeric'),
    ('morning_energy',  'How is your energy level this morning? (1-10)',        'numeric'),
    ('mood',            'How would you rate your overall mood? (1-10)',         'numeric'),
    ('exercise',        'Did you exercise today?',                              'boolean'),
    ('stress',          'How would you rate your stress level? (1-10, 10=most)', 'numeric')
ON CONFLICT (name) DO NOTHING;
