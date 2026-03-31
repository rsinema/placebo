# Placebo — Implementation Plan

## Context
Build a personal health tracking system: Telegram bot for daily check-ins + experiment tracking, Postgres for storage, React dashboard for analytics. Designed for single-user local deployment with Docker Compose.

---

## Monorepo Layout

```
placebo/
  docker-compose.yml
  .env.example
  .env                          # git-ignored
  README.md
  project_spec.md               # already exists

  db/
    init.sql                    # DDL, run on first container start

  bot/
    pyproject.toml              # uv project
    Dockerfile
    src/
      placebo_bot/
        __init__.py
        main.py                 # entrypoint
        config.py               # pydantic-settings
        db.py                   # asyncpg pool + queries
        models.py               # dataclasses for domain objects
        telegram_handler.py     # python-telegram-bot handlers
        scheduler.py            # check-in scheduling via JobQueue
        agent/
          __init__.py
          graph.py              # LangGraph StateGraph
          nodes.py              # node functions
          state.py              # TypedDict for graph state
          prompts.py            # prompt templates
    tests/

  api/
    pyproject.toml
    Dockerfile
    src/
      placebo_api/
        __init__.py
        main.py                 # FastAPI app
        config.py
        db.py
        routes/
          metrics.py
          experiments.py
          checkins.py
    tests/

  dashboard/
    package.json
    Dockerfile
    vite.config.ts
    src/
      main.tsx
      App.tsx
      api/client.ts
      components/
        Layout.tsx
        MetricChart.tsx
        ExperimentMarkers.tsx
        CorrelationPlot.tsx
        ComparisonView.tsx
        DateRangeFilter.tsx
      pages/
        Dashboard.tsx
        MetricDetail.tsx
        Experiments.tsx
      hooks/
        useMetrics.ts
        useCheckins.ts
        useExperiments.ts
```

---

## Phase 1: Project Skeleton & Database

- [x] **Status: Complete**

**Goal:** docker-compose boots Postgres with schema, plus stub bot and API containers.

### What to build
- **`docker-compose.yml`** — 4 services: `db` (postgres:16-alpine), `bot`, `api`, `dashboard`. Named volume `pgdata`. Health check on Postgres via `pg_isready`. Bot/API depend on `db` with `condition: service_healthy`.
- **`.env.example`** — `TELEGRAM_BOT_TOKEN`, `MOONSHOT_API_KEY`, `POSTGRES_*`, `DATABASE_URL`, `CHECKIN_HOUR`, `CHECKIN_MINUTE`, `LANGSMITH_API_KEY` (optional), `LANGSMITH_PROJECT` (optional).
- **`db/init.sql`** — Full DDL:
  - `pgcrypto` extension for `gen_random_uuid()`
  - `response_type_enum` (`numeric`, `boolean`, `text`)
  - `metrics`, `checkin_responses`, `experiments` tables per spec
  - `bot_settings` table (key/value) for persisting chat_id and schedule config
  - Index on `checkin_responses(metric_id, logged_at)`
  - Seed a few starter metrics (sleep quality, morning energy, mood, exercise, stress)
- **`bot/`** — `pyproject.toml` with deps (`python-telegram-bot[job-queue]`, `asyncpg`, `pydantic-settings`, `langchain-openai`, `langgraph`, `langchain-core`). Dockerfile. Stub `main.py` that just prints "Bot starting".
- **`api/`** — `pyproject.toml` with deps (`fastapi`, `uvicorn[standard]`, `asyncpg`, `pydantic-settings`). Dockerfile. Stub `main.py` with `/health` endpoint.
- **`dashboard/`** — `package.json` with deps (`react`, `react-dom`, `react-router-dom`, `recharts`, `date-fns`). Dockerfile (bun build + nginx). Stub app.
- **`README.md`** — Setup instructions.

### Verification
`docker compose up --build` starts all containers. Postgres has schema + seed data. `curl localhost:8000/health` returns OK.

---

## Phase 2: Database Access Layer

- [x] **Status: Complete**

**Goal:** Async DB query functions for both bot and API.

### Bot (`bot/src/placebo_bot/db.py`)
- `asyncpg` connection pool init/teardown
- Write + read queries: `get_active_metrics()`, `get_metric_by_name()`, `create_metric()`, `archive_metric()`, `save_checkin_response()`, `get_active_experiments()`, `create_experiment()`, `end_experiment()`, `get/set_bot_setting()`

### Bot models (`bot/src/placebo_bot/models.py`)
- Dataclasses: `Metric`, `CheckinResponse`, `Experiment`

### API (`api/src/placebo_api/db.py`)
- Separate pool, read-only queries: `get_metrics()`, `get_checkin_responses()`, `get_experiments()`, `get_metric_stats()`, `get_correlation_data()`

### Design note
Duplicating pool setup across bot/api is intentional for v1 simplicity. The API only needs reads; the bot needs reads + writes. Extract a shared package later if duplication becomes painful.

---

## Phase 3: Telegram Bot Core

- [x] **Status: Complete**

**Goal:** Working bot that receives messages and runs scheduled jobs.

### Key files
- **`telegram_handler.py`** — Build `Application`, register `/start` (welcome + persist chat_id), `/help`, and a catch-all `MessageHandler` that routes text to the LangGraph agent.
- **`scheduler.py`** — Uses `python-telegram-bot`'s `JobQueue` to schedule daily check-ins at the configured time. A `/setcheckin HH:MM` command to reschedule dynamically (persisted to `bot_settings` table).
- **`main.py`** — Init DB pool, build Telegram app, register handlers, schedule check-in, `run_polling()`.

### Chat ID persistence
On `/start`, save `chat_id` to `bot_settings` table. The scheduler reads it from there to know where to send the daily check-in.

---

## Phase 4: LangGraph Agent (core of the bot)

- [x] **Status: Complete**

**Goal:** LLM-powered intent classification, multi-turn check-in flow, metric/experiment management.

### Graph structure
```
[entry] -> classify_intent
  -> "checkin_response"  -> process_checkin -> ask_next_question (or complete)
  -> "add_metric"        -> handle_add_metric -> (awaits confirmation)
  -> "remove_metric"     -> handle_remove_metric
  -> "show_metrics"      -> handle_show_metrics
  -> "start_experiment"  -> handle_start_experiment
  -> "end_experiment"    -> handle_end_experiment
  -> "show_experiments"  -> handle_show_experiments
  -> "skip_today"        -> handle_skip
  -> "set_schedule"      -> handle_set_schedule
  -> "general"           -> handle_general (freeform LLM response)
```

### State (`agent/state.py`)
```python
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    intent: str
    chat_id: int
    checkin_active: bool
    checkin_metrics: list[dict]
    checkin_current_index: int
    checkin_responses: list[dict]
    pending_metric: dict | None
    response_text: str
```

### Nodes (`agent/nodes.py`)
- **`classify_intent`** — Claude Haiku classifies user message into one of the known intents. If `checkin_active=True` and not a command override, defaults to `checkin_response`.
- **`process_checkin_response`** — Claude Haiku extracts structured value (number/bool/text) from free-text answer. Saves to DB. Increments index.
- **`ask_next_question`** — Returns next metric's `question_prompt`, or completion message if done.
- **`start_checkin`** — Fetches active metrics, populates state, returns first question.
- **`handle_add_metric`** — Claude Haiku generates name/question/response_type from natural language. Stores in `pending_metric`, asks user to confirm.
- **`confirm_metric`** — On user confirmation, saves to DB.
- **`handle_remove_metric`** — Finds metric by name, calls `archive_metric()`.
- **`handle_start_experiment`** — Creates experiment. Warns if overlapping experiments exist.
- Other nodes are straightforward DB reads formatted as text.

### Prompts (`agent/prompts.py`)
- `CLASSIFY_INTENT_PROMPT` — Intent classification with structured JSON output
- `PARSE_CHECKIN_RESPONSE_PROMPT` — Extract value from conversational answer
- `GENERATE_METRIC_PROMPT` — Generate metric definition from description
- `GENERAL_CHAT_PROMPT` — Freeform health-related conversation

### State persistence between messages
In-memory dict keyed by `chat_id`. Hydrate before graph invocation, dehydrate after. Fine for single-user. The scheduler triggers check-in by setting `checkin_active=True` and invoking `start_checkin` directly.

### Integration with telegram_handler
`handle_message`: load state -> build `AgentState` -> `agent_graph.invoke()` -> extract `response_text` -> persist state -> send message.

---

## Phase 5: API Layer

- [x] **Status: Complete**

**Goal:** FastAPI backend serving dashboard data.

### Routes
- `GET /api/metrics` — list metrics (query param `include_archived`)
- `GET /api/metrics/{id}/responses` — time-series data with `start`/`end` params
- `GET /api/metrics/{id}/stats` — avg, min, max, count over date range
- `GET /api/metrics/correlation` — paired values for two metrics by date
- `GET /api/experiments` — list all experiments
- `GET /api/experiments/{id}/comparison` — metric averages "before" vs "during"
- `GET /api/checkins/latest` — most recent check-in set

### Setup
- CORS middleware (allow `*` since local only)
- Lifespan handler for DB pool init/close
- Pydantic response models for type safety

---

## Phase 6: React Dashboard

- [x] **Status: Complete**

**Goal:** Analytics UI with charts, experiment overlays, and correlation views.

### Pages
- **Dashboard (`/`)** — All active metrics as stacked `LineChart`s with experiment period overlays. Global `DateRangeFilter`.
- **MetricDetail (`/metrics/:id`)** — Larger chart for one metric + stats (avg/min/max).
- **Experiments (`/experiments`)** — List of experiments. Click one to see `ComparisonView` (bar chart: before vs during averages). `CorrelationPlot` (scatter chart) at bottom.

### Components
- `MetricChart` — Recharts `LineChart` + `ReferenceArea` for experiment bands
- `ComparisonView` — Recharts `BarChart` with grouped bars
- `CorrelationPlot` — Recharts `ScatterChart` with metric selector dropdowns
- `DateRangeFilter` — Pair of date inputs
- `Layout` — Simple nav (Dashboard, Experiments)

### Data fetching
Simple `useEffect` + `useState` hooks per resource. Typed fetch wrapper in `api/client.ts`. No React Query for v1.

### Vite config
Proxy `/api` to `http://localhost:8000` for local dev. In Docker, nginx handles the proxy.

---

## Phase 7: Docker Compose Finalization & Polish

- [x] **Status: Complete**

**Goal:** Everything runs together with `docker compose up`.

- Finalize all Dockerfiles (multi-stage where appropriate)
- Ensure service dependencies and health checks work
- Dashboard Dockerfile: bun build -> nginx serving static files, with nginx config proxying `/api` to the api container
- Verify end-to-end flow: bot sends check-in, user responds, data appears on dashboard

---

## TODO (Future)
- [ ] Set up LangSmith account and configure API key for LLM observability
- [ ] Add `experiment_metrics` join table if relevant-metric tagging becomes needed
- [ ] Consider extracting shared DB package if duplication between bot/api becomes painful
- [ ] Add basic auth if deploying beyond local network
- [ ] Migration tooling (beyond init.sql) if schema evolves significantly

---

## Verification (end-to-end)
1. `cp .env.example .env` and fill in `TELEGRAM_BOT_TOKEN` + `MOONSHOT_API_KEY`
2. `docker compose up --build`
3. Send `/start` to the Telegram bot — should get welcome message
4. Wait for scheduled check-in (or send "start check-in") — multi-turn Q&A flow
5. Send "add metric for hydration" — bot proposes a metric, user confirms
6. Send "start experiment: creatine 5g daily" — bot creates experiment
7. Open `http://localhost:3000` — dashboard shows seeded metrics and any logged data
8. Charts display experiment periods as shaded bands
