# Placebo

A personal health tracking system for running self-experiments on supplements, diet, and behavioral changes. A Telegram bot handles daily check-ins and experiment management through natural conversation, stores everything in Postgres, and a React dashboard visualizes the data over time.

## Why

I wanted a way to actually measure whether the things I try — creatine, cold exposure, new sleep routines — are doing anything or if I'm just experiencing the placebo effect. Most health apps track one thing well but don't let you overlay experiments against subjective metrics over time. Placebo is built around that workflow: define what you want to track, run named experiments, and compare the data.

## How It Works

### Telegram Bot
The bot is the primary interface. It sends a daily check-in at a scheduled time, walking through each of your active metrics one by one ("How was your sleep quality? (1-10)", "Did you exercise today?", etc.). You respond conversationally and a LangGraph agent powered by an LLM parses your answers into structured data.

Beyond check-ins, you manage everything through natural language:
- **Metrics** — "add a metric for afternoon energy" or "remove the stress metric"
- **Experiments** — "start experiment: creatine 5g daily" or "end experiment: creatine"
- **Schedule** — adjust when your daily check-in fires

The bot warns you when overlapping experiments make attribution harder and suggests relevant metrics when you start a new experiment.

### Dashboard
A React frontend with Recharts for visualizing your data:
- **Time-series charts** for each metric with experiment periods shown as shaded overlays
- **Experiment comparison** — bar charts showing average metric values before vs. during an experiment
- **Correlation plots** — scatter charts to spot relationships between any two metrics
- **Date range filtering** across all views

### Architecture
The stack is four Docker containers wired together with Compose:
- **Bot** — Python, `python-telegram-bot`, LangGraph agent for intent classification and multi-turn flows
- **API** — FastAPI serving read-only endpoints for the dashboard
- **Dashboard** — Vite + React, served via nginx which also proxies API requests
- **Postgres** — stores metrics, check-in responses, and experiments

Everything runs locally with `docker compose up`. Single-user by design — no auth overhead.

## Setup

1. Copy the example env file and fill in your tokens:

   ```bash
   cp .env.example .env
   ```

   Required values:
   - `TELEGRAM_BOT_TOKEN` — from [@BotFather](https://t.me/BotFather)
   - `MOONSHOT_API_KEY` — from [Moonshot AI Platform](https://platform.moonshot.cn/)

2. Start all services:

   ```bash
   docker compose up --build
   ```

3. Send `/start` to your Telegram bot to initialize, then start tracking.

## Services

| Service | URL |
|---|---|
| Dashboard | http://localhost:3000 |
| API | http://localhost:8000 |
| API Health Check | http://localhost:8000/health |
| Postgres | localhost:5432 |

## Project Structure

```
placebo/
  docker-compose.yml
  db/init.sql              # Database schema + seed data
  bot/                     # Telegram bot (Python, LangGraph)
  api/                     # FastAPI backend
  dashboard/               # React + Recharts frontend
```
