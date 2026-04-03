# Placebo — Agent Guide

Personal health tracking system: a Telegram bot for daily check-ins via natural language, a FastAPI read-only backend, and a React dashboard with Recharts for visualization.

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Telegram   │────▶│    Bot      │────▶│  Postgres   │
│   Users     │◀────│ (LangGraph) │     │   (db/)    │
└─────────────┘     └─────────────┘     └─────────────┘
                                              │
┌─────────────┐     ┌─────────────┐            │
│  Dashboard  │◀───▶│    API      │◀───────────┘
│  (React)    │     │ (FastAPI)   │
│  nginx:3000 │     │ port 8000   │
└─────────────┘     └─────────────┘
```

**Bot** — Python 3.12, `python-telegram-bot` v21+, LangGraph agent. Receives messages, classifies intent via Moonshot LLM, executes actions (check-ins, metric management, experiments). State is in-memory keyed by `chat_id`.

**API** — FastAPI, read-only endpoints for dashboard. Shares the Postgres DB with the bot.

**Dashboard** — React 19 + Vite + Recharts. Served by nginx in production, Vite dev proxy in development.

## Essential Commands

```bash
# Full stack (from repo root)
docker compose up --build

# Dashboard dev (hot reload)
cd dashboard && bun install && bun run dev

# API dev (from repo root)
cd api && uv sync && uv run uvicorn placebo_api.main:app --reload --port 8000

# Bot dev (from repo root)
cd bot && uv sync && uv run python -m placebo_bot.main

# Test Moonshot API connectivity
cd bot && uv run python src/placebo_bot/test_moonshot.py

# Lint (bot + api)
cd bot && uv run ruff check src/
cd api && uv run ruff check src/
```

## Project Structure

```
placebo/
├── db/init.sql              # Postgres schema + seed metrics
├── docker-compose.yml       # All 4 services (db, bot, api, dashboard)
├── .env.example             # Template for .env
├── bot/                     # Telegram bot (Python)
│   ├── pyproject.toml       # uv-managed deps
│   ├── Dockerfile
│   └── src/placebo_bot/
│       ├── main.py          # Entry point, ApplicationBuilder, handlers
│       ├── telegram_handler.py  # Handlers + in-memory state store
│       ├── scheduler.py     # Daily JobQueue scheduling
│       ├── db.py            # asyncpg pool + all DB queries
│       ├── models.py        # dataclass models (Metric, Experiment, etc.)
│       ├── config.py        # pydantic-settings
│       └── agent/
│           ├── graph.py     # LangGraph StateGraph construction
│           ├── nodes.py     # All node functions (async)
│           ├── state.py     # AgentState TypedDict
│           └── prompts.py    # LLM prompt strings
├── api/                     # FastAPI backend
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── src/placebo_api/
│       ├── main.py          # FastAPI app, CORS, routers
│       ├── db.py            # asyncpg pool + read-only queries
│       ├── config.py
│       └── routes/
│           ├── metrics.py    # /metrics/* + /metrics/correlation
│           ├── experiments.py # /experiments/*
│           └── checkins.py   # /checkins/latest
└── dashboard/               # React frontend
    ├── package.json         # bun-managed
    ├── Dockerfile           # bun build → nginx
    ├── nginx.conf           # Serves SPA, proxies /api/ to api:8000
    ├── vite.config.ts       # Dev proxy: /api → localhost:8000
    └── src/
        ├── api/client.ts    # All fetch helpers, BASE="/api"
        ├── pages/          # Dashboard, MetricDetail, Experiments
        ├── components/      # MetricChart, CorrelationPlot, ComparisonView, etc.
        └── hooks/           # useMetrics, useExperiments, useCheckins
```

## Code Conventions

### Python (bot, api)

- **Package layout**: `src/<package_name>/` with `src/<package_name>/__init__.py`
- **DB access**: `asyncpg` pool pattern — `init_pool()` at startup, `close_pool()` on shutdown, `_get_pool()` helper. Both bot and api have their own `db.py` (not shared).
- **Settings**: `pydantic-settings` `BaseSettings`, loaded from `.env` via `env_file` in docker-compose
- **Dataclasses over Pydantic models** for internal domain objects (`models.py`)
- **Ruff linting**: configured via pyproject.toml (no explicit ruff.toml)
- **Key import**: `from placebo_bot import db` inside functions to avoid circular imports

### TypeScript (dashboard)

- React 19 with hooks pattern, no class components
- Custom hooks in `hooks/` for data fetching
- API client (`api/client.ts`) is the single source of all HTTP calls
- Routing via `react-router-dom` v7 with nested routes under `Layout`

## Bot: Agent Architecture

The bot uses **LangGraph's `StateGraph`** with a custom routing function `_route_intent()` in `graph.py`. This is not a standard ReAct agent — it's a **directed graph with conditional edges** based on intent classification.

### Flow

```
Message → classify_intent → [intent router] → [specific node] → END
                                      ↑
                            (if checkin_active → process_checkin_response → ask_next_or_complete → END)
```

### State (`AgentState`)

- `messages`: `Annotated[list, add_messages]` — recent conversation history
- `checkin_active`, `checkin_metrics`, `checkin_current_index`, `checkin_responses`: check-in flow state
- `pending_metric`: metric awaiting user confirmation (two-step add flow)
- `intent`, `chat_id`, `response_text`

### In-memory state

The bot stores per-user state in a module-level dict (`_state_store: dict[int, dict]`) keyed by `chat_id`. This means **state resets on bot restart**. The LangGraph agent is invoked with `ainvoke(state)` on each message.

### LLM Integration

- **Provider**: Moonshot AI (Kimi), not OpenAI
- **Model**: `kimi-k2-0905-preview`
- **Base URL**: `https://api.moonshot.ai/v1` (hardcoded in `nodes.py`)
- **Package**: `langchain_openai.ChatOpenAI` (works with Moonshot's OpenAI-compatible API)
- **JSON parsing**: `_parse_json()` strips markdown code fences before `json.loads`
- **Two LLM instances**: `_llm` (max_tokens=256) for classification/parsing, `_llm_general` (max_tokens=1024) for general chat

### Intent Routing Gotcha

The routing function `_route_intent` is defined in `graph.py` but references node functions imported from `nodes.py`. If new nodes are added, they must be:
1. Imported at the top of `graph.py`
2. Added to the conditional edges dict in `add_conditional_edges`
3. Added to the terminal edges list

The routing function itself is passed to `add_conditional_edges` and called with `state: AgentState`.

### Check-in Flow

1. `start_checkin` → fetches active metrics, sets `checkin_active=True`
2. User responds → `classify_intent` sees `checkin_active` + valid index → routes to `process_checkin_response`
3. `process_checkin_response` → LLM parses answer → saves to DB → updates index
4. `ask_next_or_complete` → if more metrics, asks next question; else ends
5. All check-in nodes use `END` as terminal (no cycle back to classify_intent within a check-in)

## Database

### Schema (Postgres 16)

- **`metrics`** — id (UUID), name, question_prompt, response_type (enum), active, created_at, archived_at
- **`checkin_responses`** — id (UUID), metric_id (FK), response_value (TEXT), notes, logged_at. Index on `(metric_id, logged_at)`
- **`experiments`** — id (UUID), name, hypothesis, started_at, ended_at
- **`bot_settings`** — key/value store for chat_id, checkin_hour, checkin_minute

### Gotchas

- `response_value` is **always TEXT** in the DB (numeric values stored as strings like `"7"`), cast to float in API queries
- `archived_at` on metrics (soft delete) — use `active_only=False` in `get_metric_by_name` when reactivating
- `checkin_hour`/`checkin_minute` stored as strings in `bot_settings` despite being integers in config

## API

- **Read-only by design** — no POST/PUT/DELETE endpoints
- All endpoints are async with `asyncpg`
- Query params for date filtering: `start` and `end` as ISO datetime strings
- Correlation endpoint joins on `logged_at::date` — only pairs same-day responses
- Experiment comparison uses a "before window" equal in duration to the experiment period

## Dashboard

- `BASE = "/api"` in the client — relies on nginx proxy or Vite dev proxy
- Date range filter shared across all views via component composition (not global state)
- Experiment overlays on time-series charts are shaded regions driven by experiment `started_at`/`ended_at` dates
- No authentication — single-user, served locally

## Env Variables

| Variable | Service | Notes |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | bot | From @BotFather |
| `MOONSHOT_API_KEY` | bot | From platform.moonshot.cn |
| `DATABASE_URL` | bot, api | `postgresql://placebo:placebo@db:5432/placebo` in Docker |
| `CHECKIN_HOUR`, `CHECKIN_MINUTE` | bot | Defaults: 14, 0 (UTC) |
| `LANGSMITH_API_KEY` | bot | Optional; not wired up in code yet |

## Testing

- No pytest/test configuration found in bot or api
- `bot/src/placebo_bot/test_moonshot.py` is a standalone Moonshot API connectivity check, not a test suite
- Dashboard has no test setup

## Future Work (TODO.txt)

- Analytics bot (separate Telegram bot with read-only DB access)
- Multi-turn conversation improvements (supervisor pattern)
- Multiple LLM provider support (OpenAI, Anthropic, Grok, etc.)
- LangSmith integration for prompt management
- Pre-commit checks with pre-commit hooks
- Gym tracking extension (lift logging via natural language)
