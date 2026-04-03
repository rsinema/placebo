# Analytics Bot — Implementation Plan

A second Telegram bot (`analytics_bot`) that is **read-only**, queries the Postgres DB directly, and can answer analytical questions reactively (user asks) or proactively (weekly digest). Generates matplotlib charts and sends them as Telegram photos.

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────┐
│  Telegram   │────▶│  Analytics Bot   │────▶│  Postgres   │
│   User      │◀────│  (LangGraph,     │◀────│  (read-    │
│             │     │   matplotlib)    │     │   only)    │
└─────────────┘     └──────────────────┘     └─────────────┘
```

---

## High-Level Summary

- **LLM:** Same `MOONSHOT_API_KEY` as existing bot, same `kimi-k2-0905-preview` model
- **DB access:** Direct `asyncpg` queries (not via API) — full analytical query flexibility
- **Interaction:** Reactive (user asks analytical questions) + Proactive (weekly digest)
- **Charting:** `matplotlib` with `Agg` headless backend, PNG via `BytesIO` → Telegram `InputFile`
- **Analysis types:** Trend, single-metric summary, correlation, experiment analysis, multi-metric overview, period comparison, streak/consistency, correlation ranking, boolean frequency

---

## Phase 0: Project Scaffold + Dependencies

**New directory:** `analytics_bot/` — mirrors the existing `bot/` structure.

**New env vars** (in `.env.example` and `docker-compose.yml`):
```
ANALYTICS_BOT_TOKEN=...          # separate bot token from @BotFather
ANALYTICS_DIGEST_DAY=0           # day-of-week for weekly digest (0=Monday)
ANALYTICS_DIGEST_HOUR=9          # UTC hour
ANALYTICS_DIGEST_MINUTE=0
```

**`analytics_bot/pyproject.toml`** adds to existing bot deps:
- `python-telegram-bot[job-queue]>=21.0`
- `asyncpg>=0.30.0`
- `pydantic-settings>=2.0`
- `langchain-openai>=0.3.0`
- `langgraph>=0.3.0`
- `matplotlib>=3.8`

**`analytics_bot/Dockerfile`** — identical pattern to existing bot:
```
FROM python:3.12-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml .
RUN uv sync --no-dev --no-install-project
COPY src/ src/
RUN uv sync --no-dev
CMD ["uv", "run", "python", "-m", "placebo_analytics.main"]
```

**`docker-compose.yml`** — add `analytics_bot` service:
```yaml
analytics_bot:
  build: ./analytics_bot
  restart: unless-stopped
  env_file: .env
  depends_on:
    db:
      condition: service_healthy
```

**DB permissions:** The existing `placebo` Postgres user covers both bots. The analytics bot code must use only `SELECT` queries — no writes to the DB.

---

## Phase 1: Core Skeleton

**Files:**

| File | Purpose |
|---|---|
| `src/placebo_analytics/__init__.py` | Package init |
| `src/placebo_analytics/main.py` | Entry point, `ApplicationBuilder`, `post_init` (init pool + schedule digest), `post_shutdown` (close pool). Registers `/start`, `/help`, text handler |
| `src/placebo_analytics/config.py` | `Settings` with `analytics_bot_token`, `moonshot_api_key`, `database_url`, `digest_day`, `digest_hour`, `digest_minute`. Reads from env |
| `src/placebo_analytics/models.py` | `Metric`, `CheckinResponse`, `Experiment` — same dataclasses as existing bot |
| `src/placebo_analytics/telegram_handler.py` | `start_command` (stores `analytics_chat_id` in `bot_settings`), `help_command`, `handle_message`. Injects messages into agent graph |

---

## Phase 2: Read-Only DB Layer

**`src/placebo_analytics/db.py`** — `asyncpg` pool, read-only queries. Key new queries not in the existing API:

**Rolling average + trend:**
```sql
SELECT
    logged_at::date AS date,
    avg(response_value::float) AS avg_value
FROM checkin_responses
WHERE metric_id = $1
  AND logged_at >= NOW() - INTERVAL '30 days'
GROUP BY date
ORDER BY date
```

**Trend direction** (computed from linear slope of last N points):
```sql
-- Pass last N (date ordinal, response_value) pairs to Python for slope calc
SELECT
    extract(epoch from (logged_at::date - '1970-01-01'::date)) / 86400 AS days_since_epoch,
    response_value::float AS value
FROM checkin_responses
WHERE metric_id = $1
ORDER BY logged_at DESC
LIMIT $2
```

**Consistency / streak** — count days with data vs. total days in window, longest consecutive logging streak.

**Multi-pair correlation ranking** — cross-join all numeric metric pairs, compute Pearson correlation, return top N pairs.

**Period comparison** — "this week vs. last week": two time windows, avg per metric, percent change.

**Weekly aggregation** — roll up daily averages into weekly averages for cleaner charts.

**All functions are `SELECT` only.** `init_pool` / `close_pool` / `_get_pool` pattern identical to existing code.

---

## Phase 3: Chart Generation

**`src/placebo_analytics/charts.py`** — all matplotlib generation.

**Critical: Headless backend.** Must be set before any matplotlib import:
```python
import matplotlib
matplotlib.use("Agg")  # Must be before pyplot import
import matplotlib.pyplot as plt
```

**Styling:** Match dashboard aesthetics — white background, clean axis labels, a color palette defined as module constants.

**Chart types:**

| Function | Use case | Type |
|---|---|---|
| `metric_time_series(metric, responses, trend_days=7)` | Single metric over time with 7-day rolling avg line | Line |
| `experiment_comparison(comparison_data)` | Before vs. during experiment per metric | Grouped bar |
| `correlation_scatter(points, metric_a_name, metric_b_name)` | Scatter plot with trend line + Pearson r | Scatter |
| `week_comparison(this_week, last_week, metrics)` | Side-by-side weekly bars | Grouped bar |
| `multi_metric_overview(metric_summaries)` | Summary dashboard — small multiples | Grid of mini-charts |
| `weekly_digest(chart_paths, metric_summaries, experiment_status)` | Full digest composite | Composite image |

**Output:** Each function returns `bytes` (PNG). No disk writes — bytes go directly to `io.BytesIO` and then to Telegram's `InputFile`.

**Size constraints:** Charts sized ~800×400px (Telegram friendly, < 2MB PNG).

**Cleanup:** All `BytesIO` objects managed in `try/finally` to ensure no fd leaks.

---

## Phase 4: Intent Classification + Agent Nodes

**`src/placebo_analytics/agent/state.py`** — `AnalyticsState` TypedDict:
```python
class AnalyticsState(TypedDict):
    messages: Annotated[list, add_messages]
    intent: str
    chat_id: int
    response_text: str
    chart_bytes: bytes | None  # PNG image to send alongside text
    suggested_followups: list[str]  # e.g. ["Want to see the 30-day trend?"]
```

**`src/placebo_analytics/agent/prompts.py`** — prompt strings:
- `CLASSIFY_ANALYTICS_INTENT` — classifies into one of 9 intents
- `SYNTHESIZE_METRIC_SUMMARY` — given stats, trend, context → natural language summary
- `SYNTHESIZE_CORRELATION` — given r-value + scatter points → what it means
- `SYNTHESIZE_EXPERIMENT_ANALYSIS` — given before/during data → was the experiment effective?
- `GENERATE_DIGEST_NARRATIVE` — given weekly summaries for all metrics → digestible digest text

**`src/placebo_analytics/agent/nodes.py`** — all node functions:

| Node | Responsibility |
|---|---|
| `classify_intent` | LLM call → JSON intent |
| `handle_metric_summary` | DB stats query → chart → LLM summary synthesis |
| `handle_trend` | DB rolling-avg + slope query → chart → trend direction + narrative |
| `handle_correlation` | DB correlation query → scatter chart → LLM interpretation |
| `handle_experiment_analysis` | DB comparison query → bar chart → LLM verdict |
| `handle_multi_metric_overview` | DB aggregate query → composite chart → overview text |
| `handle_period_comparison` | DB period query → comparison chart → narrative |
| `handle_streak` | DB streak query → text response |
| `handle_correlation_ranking` | DB cross-correlation query → ranked list text |
| `handle_general` | Freeform analytical question → DB queries as needed + LLM synthesis |

**LLM sharing:** `nodes.py` creates two `ChatOpenAI` instances pointing at `https://api.moonshot.ai/v1` with the shared `MOONSHOT_API_KEY`, same model `kimi-k2-0905-preview`. Max tokens: 256 for classification, 1024 for synthesis.

**`_parse_json`** — same as existing bot (strips markdown fences).

**`chart_bytes` in state:** Nodes that generate charts set `chart_bytes` in the returned dict. `telegram_handler.py` reads it after `ainvoke` and sends the photo if present.

**`suggested_followups`:** Each node can return 1-2 follow-up questions to guide the conversation.

**`src/placebo_analytics/agent/graph.py`** — same `StateGraph` pattern as existing bot. Conditional edges from `classify_intent` to the 9 handler nodes. All handler nodes → `END`. No check-in-like loops — the analytics bot is stateless Q&A per message.

---

## Phase 5: Weekly Digest

**`src/placebo_analytics/scheduler.py`** — analogous to existing `scheduler.py`:

```python
async def _weekly_digest_job(context) -> None:
    chat_id_str = await db.get_bot_setting("analytics_chat_id")
    if not chat_id_str:
        return
    chat_id = int(chat_id_str)

    # Fetch data for all active metrics (last 7 days)
    # Generate charts for each metric
    # Synthesize narrative with LLM
    # Send: text message + charts (multiple photos, Telegram allows up to 10)
    # Fallback: if too many charts, send as album or reduce count

def schedule_digest(app: Application, day: int, hour: int, minute: int) -> None:
    job_queue.run_weekly(
        _weekly_digest_job,
        day=day,  # 0=Monday, 6=Sunday
        time=time(hour=hour, minute=minute),
        name="weekly_digest",
    )
```

**Digest content per week:**
1. Per-metric summaries: avg, min, max, trend direction, consistency %
2. One chart per metric (time series, 7-day rolling avg)
3. Active experiment status update (if any)
4. Top 2 strongest correlations discovered this week
5. Narrative paragraph synthesized by LLM

**Resilience:** If Moonshot API fails during digest, send a text-only version with the stats. If DB query fails, log and skip. Never crash silently.

---

## Phase 6: Wiring + Error Handling

**`telegram_handler.py`** `handle_message` flow:
```
1. Get/inject state (stateless per message — no persistent state needed)
2. state["messages"] = last 5 messages (rolling window for context)
3. result = await agent_graph.ainvoke(state)
4. If result["response_text"]: send text
5. If result["chart_bytes"]: send photo (InputFile from BytesIO)
6. If result["suggested_followups"]: append as second message
```

**Rate limiting:** Short-circuit if user sends >5 messages in 10 seconds (simple in-memory counter).

**Error handling:** Wrap `ainvoke` in try/except. On failure, log + send "I had trouble analyzing that. Try rephrasing?"

---

## Phase 7: Testing + Polish

- `cd analytics_bot && uv run python src/placebo_analytics/test_moonshot.py` — Moonshot connectivity
- `cd analytics_bot && uv run ruff check src/` — lint
- Manual Telegram test: ask a variety of queries across all 9 intents
- Verify chart rendering locally (save `chart_bytes` to file in dev, compare to Telegram output)
- Verify weekly digest fires correctly (can test by temporarily setting `DIGEST_DAY` to current day)
- Docker: verify matplotlib `Agg` backend works in the slim image (no display dependency needed)

---

## Files to Create

```
analytics_bot/pyproject.toml
analytics_bot/Dockerfile
analytics_bot/src/placebo_analytics/__init__.py
analytics_bot/src/placebo_analytics/main.py
analytics_bot/src/placebo_analytics/config.py
analytics_bot/src/placebo_analytics/models.py
analytics_bot/src/placebo_analytics/telegram_handler.py
analytics_bot/src/placebo_analytics/scheduler.py
analytics_bot/src/placebo_analytics/db.py
analytics_bot/src/placebo_analytics/charts.py
analytics_bot/src/placebo_analytics/agent/__init__.py
analytics_bot/src/placebo_analytics/agent/state.py
analytics_bot/src/placebo_analytics/agent/prompts.py
analytics_bot/src/placebo_analytics/agent/graph.py
analytics_bot/src/placebo_analytics/agent/nodes.py
```

## Files to Modify

```
.env.example              — add ANALYTICS_BOT_TOKEN, ANALYTICS_DIGEST_*
docker-compose.yml        — add analytics_bot service
AGENTS.md                 — document the new service and commands
```

---

## Non-Obvious Decisions

1. **`matplotlib.use("Agg")` must be set before `import matplotlib.pyplot`** — this is the #1 pitfall when adding matplotlib to a headless/Docker service. It must be the very first matplotlib-related line in `charts.py`.

2. **No persistent conversation state** — the analytics bot doesn't need `_state_store` with complex state like the check-in bot. Each message is stateless. Only the weekly digest scheduler needs stored `analytics_chat_id` in `bot_settings`.

3. **Charts sent as `InputFile` from `BytesIO`** — never write to disk in Docker. `bot.send_photo(photo=InputFile(bytes_io, filename="chart.png"))` handles it in-memory.

4. **Digest sends multiple photos** — Telegram allows up to 10 photos in a media group. The digest should send charts as a media group (album) + one text message before it.

5. **Same `bot_settings` table, new key** — the analytics bot stores its `chat_id` as `analytics_chat_id` to avoid colliding with the check-in bot's `chat_id`.

6. **9 intents, not 1 "general" fallback** — the analytics agent should almost always route somewhere specific. The `handle_general` node exists for unusual analytical questions, but with 9 specific intents covering the full analytical surface area, it should rarely be needed.

7. **Trend slope computed in Python** — SQL is not great at linear regression. The rolling-avg query returns `(days_since_epoch, value)` pairs, then Python computes the slope with a simple least-squares formula. This is more reliable than SQL-side approaches.

8. **`response_value::float` cast** — the DB stores all values as TEXT. Every analytical query must cast to `float` for numeric operations. Boolean values (`"true"`/`"false"`) should be excluded from numeric aggregations or handled separately (count of true days / total days).
