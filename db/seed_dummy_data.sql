-- Seed dummy data for local development/testing
-- Run with: docker exec -i placebo-db-1 psql -U placebo -d placebo -f - < db/seed_dummy_data.sql
-- Or:       docker compose exec db psql -U placebo -d placebo -f /seed_dummy_data.sql

BEGIN;

-- Clear existing response data (keep metrics)
DELETE FROM checkin_responses;
DELETE FROM experiments;

-- Grab metric IDs into temp table for reference
CREATE TEMP TABLE _metric_ids AS
SELECT id, name FROM metrics WHERE active = TRUE;

-- Generate 90 days of checkin_responses for numeric metrics
-- Uses generate_series + random() to create realistic-looking data

-- sleep_quality: tends 5-8, slight upward trend
INSERT INTO checkin_responses (metric_id, response_value, notes, logged_at)
SELECT
    m.id,
    round((5.0 + random() * 3.0 + (gs / 90.0) * 1.5)::numeric, 0)::text,
    CASE WHEN random() < 0.15 THEN 'Slept poorly, woke up multiple times'
         WHEN random() < 0.10 THEN 'Great night, fell asleep fast'
         WHEN random() < 0.08 THEN 'Tried new pillow'
         ELSE NULL END,
    (NOW() - INTERVAL '1 day' * (90 - gs))::timestamptz
        + (INTERVAL '1 hour' * (6 + floor(random() * 3)))  -- logged between 6-9am
FROM generate_series(0, 89) AS gs
CROSS JOIN _metric_ids m
WHERE m.name = 'sleep_quality'
  AND random() < 0.85;  -- ~85% consistency (skip some days)

-- morning_energy: tends 4-7, correlated loosely with sleep
INSERT INTO checkin_responses (metric_id, response_value, notes, logged_at)
SELECT
    m.id,
    round((4.0 + random() * 3.0 + (gs / 90.0) * 1.0)::numeric, 0)::text,
    CASE WHEN random() < 0.10 THEN 'Coffee helped a lot'
         WHEN random() < 0.05 THEN 'Dragging today'
         ELSE NULL END,
    (NOW() - INTERVAL '1 day' * (90 - gs))::timestamptz
        + (INTERVAL '1 hour' * (6 + floor(random() * 3)))
FROM generate_series(0, 89) AS gs
CROSS JOIN _metric_ids m
WHERE m.name = 'morning_energy'
  AND random() < 0.80;

-- mood: tends 5-8
INSERT INTO checkin_responses (metric_id, response_value, notes, logged_at)
SELECT
    m.id,
    round((5.0 + random() * 3.5)::numeric, 0)::text,
    CASE WHEN random() < 0.08 THEN 'Rough day at work'
         WHEN random() < 0.06 THEN 'Feeling great, productive day'
         ELSE NULL END,
    (NOW() - INTERVAL '1 day' * (90 - gs))::timestamptz
        + (INTERVAL '1 hour' * (18 + floor(random() * 4)))  -- logged in evening
FROM generate_series(0, 89) AS gs
CROSS JOIN _metric_ids m
WHERE m.name = 'mood'
  AND random() < 0.82;

-- exercise: boolean, ~60% yes rate
INSERT INTO checkin_responses (metric_id, response_value, notes, logged_at)
SELECT
    m.id,
    CASE WHEN random() < 0.60 THEN 'true' ELSE 'false' END,
    CASE WHEN random() < 0.12 THEN 'Went for a run'
         WHEN random() < 0.08 THEN 'Gym session'
         WHEN random() < 0.05 THEN 'Rest day'
         ELSE NULL END,
    (NOW() - INTERVAL '1 day' * (90 - gs))::timestamptz
        + (INTERVAL '1 hour' * (18 + floor(random() * 4)))
FROM generate_series(0, 89) AS gs
CROSS JOIN _metric_ids m
WHERE m.name = 'exercise'
  AND random() < 0.78;

-- stress: tends 3-7, inversely trending (improving over time)
INSERT INTO checkin_responses (metric_id, response_value, notes, logged_at)
SELECT
    m.id,
    round((7.0 - random() * 3.0 - (gs / 90.0) * 1.5)::numeric, 0)::text,
    CASE WHEN random() < 0.10 THEN 'Deadline pressure'
         WHEN random() < 0.05 THEN 'Meditation helped'
         ELSE NULL END,
    (NOW() - INTERVAL '1 day' * (90 - gs))::timestamptz
        + (INTERVAL '1 hour' * (18 + floor(random() * 4)))
FROM generate_series(0, 89) AS gs
CROSS JOIN _metric_ids m
WHERE m.name = 'stress'
  AND random() < 0.80;

-- Create two experiments
INSERT INTO experiments (name, hypothesis, started_at, ended_at)
VALUES
    ('Morning meditation', 'Daily 10-min meditation will reduce stress by 1 point on average',
     NOW() - INTERVAL '45 days', NOW() - INTERVAL '15 days'),
    ('No screens before bed', 'Avoiding screens 1hr before bed will improve sleep quality',
     NOW() - INTERVAL '20 days', NULL);

-- Drop temp table
DROP TABLE _metric_ids;

COMMIT;

-- Quick sanity check
SELECT m.name, count(cr.id) AS responses
FROM metrics m
LEFT JOIN checkin_responses cr ON cr.metric_id = m.id
GROUP BY m.name
ORDER BY m.name;
