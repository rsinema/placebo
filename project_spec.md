# Health Tracking Agent — Project Spec

## Overview
A personal health tracking system driven by a Telegram bot that conducts daily check-ins, stores responses in a database, and surfaces analytics through a dashboard. The primary goal is to support data-driven self-experimentation with supplements, diet, and behavioral changes inspired by protocols from sources like Huberman Lab.

---

## Core Features

### 1. Daily Check-in Bot (Telegram)
- A Telegram bot sends the user a scheduled daily check-in message
- The check-in asks a series of questions based on the user's currently active metrics
- The user responds conversationally; the bot parses and stores responses
- Questions should feel lightweight — prefer numeric scales (1–10) with optional freeform follow-up
- The bot should distinguish between **commands** (managing the system) and **check-in responses** (logging data)

### 2. Dynamic Metrics
- Metrics are stored in the database and drive which questions are asked during check-ins
- The user can add or remove metrics by sending natural language commands to the bot
  - e.g. "add a metric for afternoon energy" or "remove the stress metric"
- Each metric stores:
  - A name/label
  - An auto-generated or user-provided question prompt
  - The response type (numeric scale, boolean, freeform text)
  - Created/archived timestamps (soft delete — never hard delete historical data)
- On metric creation, the bot should confirm the question it will ask and allow the user to edit it

### 3. Experiments
- The user can start and stop named experiments via bot commands
  - e.g. "start experiment: creatine 5g daily" or "end experiment: creatine"
- Each experiment stores:
  - A name and optional hypothesis
  - Start and end timestamps
  - Which metrics are considered most relevant (optional tagging)
- Multiple experiments can run simultaneously, but the bot should warn the user that overlapping experiments make attribution harder
- Experiments are surfaced as markers/annotations on dashboard charts
- When starting an experiment, the bot should optionally suggest relevant metrics to add

### 4. Analytics Dashboard
- A web-based dashboard for viewing logged data over time
- Key views:
  - Time-series chart per metric with experiment markers overlaid
  - Experiment comparison view: average metric values before vs. during an experiment
  - Metric correlation view: plot two metrics against each other over time
- Date range filtering
- The dashboard should visually distinguish "baseline" periods from active experiment periods

---

## Suggested Tech Stack

### Bot & Backend
- **Language:** Python using `uv`
- **Telegram integration:** `python-telegram-bot` library
- **LLM framework:** LangChain/LangGraph for all LLM interactions and agent logic
- **LLM model:** Anthropic Claude via LangChain's Anthropic integration (claude-haiku for cost efficiency on simple tasks)
- **Observability:** LangSmith for tracing, debugging, and monitoring all LLM calls

### Database
- **Postgres** running as a Docker container
- Tables: `metrics`, `checkin_responses`, `experiments`

### Dashboard
- **Framework:** Next.js or simple React app (use `bun`)
- **Charts:** Recharts or Chart.js
- **Data access:** Direct Postgres connection or a lightweight API layer

### Containerization & Deployment
- The entire stack should be containerized with **Docker**
- A `docker-compose.yml` file should define and wire together all services:
  - `bot` — the Telegram bot/backend service
  - `db` — Postgres database
  - `dashboard` — the Next.js/React frontend
- A `.env.example` file should document all required environment variables (Telegram bot token, Claude API key, Postgres credentials, etc.)
- Deployment is left to the user — the project should run on any machine or VPS with `docker compose up`
- A basic `README.md` should include setup and launch instructions

---

## Database Schema (Initial)

### `metrics`
| Column | Type | Notes |
|---|---|---|
| id | uuid | primary key |
| name | text | e.g. "morning energy" |
| question_prompt | text | e.g. "How was your energy when you woke up? (1-10)" |
| response_type | enum | `numeric`, `boolean`, `text` |
| active | boolean | soft delete flag |
| created_at | timestamp | |
| archived_at | timestamp | nullable |

### `checkin_responses`
| Column | Type | Notes |
|---|---|---|
| id | uuid | primary key |
| metric_id | uuid | foreign key → metrics |
| response_value | text | store all as text, cast on read |
| notes | text | optional freeform addition |
| logged_at | timestamp | |

### `experiments`
| Column | Type | Notes |
|---|---|---|
| id | uuid | primary key |
| name | text | e.g. "creatine 5g daily" |
| hypothesis | text | nullable, user-defined expectation |
| started_at | timestamp | |
| ended_at | timestamp | nullable — null means ongoing |

---

## Bot Command Reference (Initial)

| Command / Phrase | Action |
|---|---|
| (scheduled trigger) | Begin daily check-in |
| `add metric [name]` | Add a new metric |
| `remove metric [name]` | Soft-delete a metric |
| `show metrics` | List all active metrics |
| `start experiment [name]` | Begin a new experiment |
| `end experiment [name]` | Close an ongoing experiment |
| `show experiments` | List all experiments |
| `skip today` | Log that check-in was skipped |

---

## Non-Functional Requirements
- The system is single-user (no auth complexity needed initially)
- All data should be owned and accessible by the user (Supabase dashboard as escape hatch)
- Bot downtime should fail gracefully — missed check-ins are noted but don't corrupt state
- Metric changes should never delete historical data

---

## Out of Scope (for now)
- Multi-user support
- Mobile app
- Wearable/automatic data ingestion (e.g. Apple Health, Oura)
- Automated statistical significance testing (manual interpretation for now)
