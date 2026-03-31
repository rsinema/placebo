# Placebo

Personal health tracking system: Telegram bot for daily check-ins and experiment tracking, Postgres for storage, React dashboard for analytics.

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

3. Services:
   - **Bot** — polls Telegram for messages
   - **API** — http://localhost:8000 (health check: `curl localhost:8000/health`)
   - **Dashboard** — http://localhost:3000
   - **Postgres** — localhost:5432

## Project Structure

```
placebo/
  docker-compose.yml
  db/init.sql          # Database schema + seed data
  bot/                 # Telegram bot (Python, LangGraph)
  api/                 # FastAPI backend for dashboard
  dashboard/           # React + Recharts frontend
```
