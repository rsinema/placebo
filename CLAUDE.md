# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Placebo is a personal health tracking system for running self-experiments on supplements, diet, and behavioral changes. A Telegram bot handles daily check-ins through natural conversation (powered by a LangGraph agent + Moonshot LLM), a FastAPI serves read-only endpoints, and a React dashboard visualizes the data with Recharts.

Single-user by design. Everything runs locally via Docker Compose.

## Architecture

Five Docker services:

- **Bot** (`bot/`) — Python, `python-telegram-bot` with JobQueue for scheduling, LangGraph agent for intent classification and multi-turn conversation flows. Connects to Postgres directly, not through the API.
- **API** (`api/`) — FastAPI, read-only endpoints (`/metrics`, `/experiments`, `/checkins`) consumed by the dashboard. Does NOT write to the DB — the bot owns all writes. Also proxies backup/restore requests to the `backup` service.
- **Dashboard** (`dashboard/`) — Vite + React + React Router + Recharts. Served by nginx which proxies `/api` requests to the FastAPI container.
- **Backup** (`backup/`) — FastAPI service on internal port 8001. Owns `pg_dump`/`pg_restore` against the DB and S3 I/O via boto3. Runs a daily cron loop in-process plus exposes `/backups` (list, create) and `/backups/{key}/restore` for the API to proxy. Never exposed to the host.
- **Postgres** (`db/migrations/`) — Stores `metrics`, `checkin_responses`, `experiments`, and `bot_settings` (key-value store for chat_id, schedule, etc.). Schema is managed by `golang-migrate/migrate`; a one-shot `migrate` Compose service runs `migrate up` against the DB on startup before the bots/API boot.

## Tooling

- **Python dependency management:** Use `uv` (not pip/poetry). Run Python commands via `uv run`.
- **Python testing:** Use `pytest`.
- **Frontend package management:** Use `bun` (not npm/yarn).

## Common Commands

```bash
# Start all services (from repo root)
docker compose up --build

# Install bot dependencies
cd bot && uv sync

# Run all bot tests
cd bot && uv run pytest -v

# Run a specific bot test file
cd bot && uv run pytest src/placebo_bot/test_scheduler.py -v
cd bot && uv run pytest src/placebo_bot/test_telegram_handler.py -v

# Rebuild a single service
docker compose up --build bot

# Install dashboard dependencies
cd dashboard && bun install

# Dashboard dev (hot reload)
cd dashboard && bun run dev
```

## Key Implementation Details

**Bot agent** (`bot/src/placebo_bot/agent/`):
- `graph.py` — LangGraph StateGraph definition with nodes for handling check-in flows, metric/experiment CRUD, and schedule changes.
- `nodes.py` — Node implementations for each conversation state (e.g., collecting check-in answers, parsing intent, responding).
- `prompts.py` — LLM prompt templates for intent classification and response parsing.
- `state.py` — LangGraph `StateSchema` defining conversation context (active metrics, pending check-in answers, etc.).

**Bot DB** (`bot/src/placebo_bot/db.py`) — Uses `asyncpg` to write check-in responses, manage metrics, and track experiments directly.

**API DB** (`api/src/placebo_api/db.py`) — Also uses `asyncpg`, but read-only. Shares the same connection pool pattern as the bot.

**Dashboard pages** (`dashboard/src/pages/`):
- `Dashboard.tsx` — Overview with time-series charts per metric, experiment overlays
- `Experiments.tsx` — Experiment comparison (before vs. during bar charts)
- `MetricDetail.tsx` — Correlation scatter plots between two metrics

**Experiment periods** are shown as shaded overlays on time-series charts — the API returns experiment time ranges and the dashboard uses the `DateRangeFilter` to clip data.

**Database schema** (`db/migrations/`): `checkin_responses` has a composite index on `(metric_id, logged_at)` — use this for efficient time-range queries per metric. See `db/MIGRATIONS.md` for the migration workflow.

## Backups

S3-backed Postgres backups. `backup` service runs daily at `BACKUP_HOUR_UTC` (default 10:00 UTC) and prunes snapshots older than `BACKUP_RETENTION_DAYS` (default 30). On-demand backup + restore from the dashboard `/backups` page; CLI fallbacks in `scripts/backup.sh` and `scripts/restore.sh`.

S3 keys are laid out as `<BACKUP_S3_PREFIX>/<kind>/<UTC timestamp>.dump.gz` where `kind` is `daily`, `manual`, or `pre-restore`. Pre-restore snapshots are taken automatically before any restore and are exempt from pruning.

## Environment Variables

Required in `.env`:
- `TELEGRAM_BOT_TOKEN` — from @BotFather
- `MOONSHOT_API_KEY` — from Moonshot AI Platform
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` — for Postgres connection (both bot and API read these)
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `BACKUP_S3_BUCKET` — for the backup service. Optional: `BACKUP_S3_PREFIX`, `BACKUP_RETENTION_DAYS`, `BACKUP_HOUR_UTC`, `BACKUP_S3_ENDPOINT_URL` (S3-compatible providers).
