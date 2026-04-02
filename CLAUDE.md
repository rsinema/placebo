# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Placebo is a personal health tracking system for running self-experiments on supplements, diet, and behavioral changes. A Telegram bot handles daily check-ins through natural conversation (powered by a LangGraph agent + Moonshot LLM), a FastAPI serves read-only endpoints, and a React dashboard visualizes the data with Recharts.

Single-user by design. Everything runs locally via Docker Compose.

## Architecture

Four Docker services:

- **Bot** (`bot/`) — Python, `python-telegram-bot` with JobQueue for scheduling, LangGraph agent for intent classification and multi-turn conversation flows. Connects to Postgres directly, not through the API.
- **API** (`api/`) — FastAPI, read-only endpoints (`/metrics`, `/experiments`, `/checkins`) consumed by the dashboard. Does NOT write to the DB — the bot owns all writes.
- **Dashboard** (`dashboard/`) — Vite + React + React Router + Recharts. Served by nginx which proxies `/api` requests to the FastAPI container.
- **Postgres** (`db/init.sql`) — Stores `metrics`, `checkin_responses`, `experiments`, and `bot_settings` (key-value store for chat_id, schedule, etc.).

## Common Commands

```bash
# Start all services (from repo root)
docker compose up --build

# Run bot tests (from bot/ dir, or repo root with pytest picked up)
cd bot && python -m pytest src/placebo_bot/test_scheduler.py -v
cd bot && python -m pytest src/placebo_bot/test_telegram_handler.py -v

# Rebuild a single service
docker compose up --build bot

# Dashboard dev (hot reload)
cd dashboard && bun install && bun run dev
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

**Database schema** (`db/init.sql`): `checkin_responses` has a composite index on `(metric_id, logged_at)` — use this for efficient time-range queries per metric.

## Environment Variables

Required in `.env`:
- `TELEGRAM_BOT_TOKEN` — from @BotFather
- `MOONSHOT_API_KEY` — from Moonshot AI Platform
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` — for Postgres connection (both bot and API read these)
