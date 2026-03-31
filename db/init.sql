-- Enable pgcrypto for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Custom enum for response types
CREATE TYPE response_type_enum AS ENUM ('numeric', 'boolean', 'text');

-- Metrics table
CREATE TABLE metrics (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL UNIQUE,
    question_prompt TEXT NOT NULL,
    response_type   response_type_enum NOT NULL DEFAULT 'numeric',
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    archived_at     TIMESTAMPTZ
);

-- Check-in responses
CREATE TABLE checkin_responses (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    metric_id       UUID NOT NULL REFERENCES metrics(id),
    response_value  TEXT NOT NULL,
    notes           TEXT,
    logged_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_checkin_responses_metric_logged
    ON checkin_responses(metric_id, logged_at);

-- Experiments
CREATE TABLE experiments (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    hypothesis  TEXT,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at    TIMESTAMPTZ
);

-- Bot settings (key/value store for chat_id, schedule, etc.)
CREATE TABLE bot_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Seed starter metrics
INSERT INTO metrics (name, question_prompt, response_type) VALUES
    ('sleep_quality',   'How would you rate your sleep quality? (1-10)',        'numeric'),
    ('morning_energy',  'How is your energy level this morning? (1-10)',        'numeric'),
    ('mood',            'How would you rate your overall mood? (1-10)',         'numeric'),
    ('exercise',        'Did you exercise today?',                              'boolean'),
    ('stress',          'How would you rate your stress level? (1-10, 10=most)', 'numeric');
