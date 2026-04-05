# Analytics Bot — Improvement Plan

Identified areas for improvement after reviewing the working prototype. Ordered roughly by user-experience impact.

---

## 1. Conversation Memory

**Problem:** Every message is completely stateless. The agent can't handle natural follow-ups like "what about over 60 days instead?", "now compare that with exercise", or "why might that be?".

**Solution:** Add a short sliding window of recent messages to the LangGraph state. LangGraph supports this via checkpointers — `MemorySaver` for dev, or a Postgres-backed checkpointer since we already have a DB. The `AnalyticsState` already has a `messages` field with `add_messages` annotation, so the wiring is partially there.

**Scope:**
- Add a LangGraph checkpointer (Postgres-backed for prod)
- Pass a `thread_id` (derived from `chat_id`) to `ainvoke` so state persists across messages
- Update the classification prompt to consider prior messages for context
- Consider a configurable window size (e.g. last 5-10 messages)

---

## 2. Metric Name Resolution

**Problem:** The LLM extracts a metric name string from the user's message, and it must exactly match something in the database. If a user says "sleep quality" but the metric is called `sleep_quality` or `Sleep`, it fails silently or returns no data.

**Solution:** Inject the list of available metric names into the classification prompt so the LLM picks from known options. Add a fuzzy matching fallback for cases where the LLM still gets it wrong.

**Scope:**
- Fetch active metric names at classification time and include them in the prompt
- Add a fuzzy match step (e.g. `difflib.get_close_matches` or Levenshtein) between the LLM's extracted name and actual DB metric names
- If no match is found, ask the user to clarify instead of returning empty results

---

## 3. Recovery from Misclassification

**Problem:** The single-pass classify-then-execute pattern means if the intent is wrong, the user gets a bad answer with no recourse. There's no confidence threshold or clarification path.

**Solution:** Add a confidence/clarification mechanism to the classification step.

**Scope:**
- Have the classification prompt return a confidence score alongside the intent
- If confidence is below a threshold, route to a clarification node that asks the user what they meant (presenting the top 2-3 candidate intents)
- Allow handler nodes to "bail out" to a clarification node instead of always routing to END (e.g. when the metric isn't found)
- Consider adding a re-classification path from the clarification node back to the router

---

## 4. Handler Error Paths

**Problem:** Handlers don't gracefully handle edge cases — insufficient data points for trend analysis, no overlapping dates for correlation, metrics with zero entries, etc. These can produce crashes, nonsensical stats, or silent failures.

**Solution:** Each handler should validate its data before computing and return a helpful message when data is insufficient.

**Scope:**
- Add minimum data checks in each handler (e.g. trend needs >= 3 points, correlation needs >= 5 overlapping dates)
- Return clear messages like "I only have 2 data points for sleep — I need at least a week of data to calculate a meaningful trend"
- Ensure `_compute_slope` and `_compute_pearson` edge cases (zero stdev, < 2 points) produce user-friendly responses, not just `None` returns that get swallowed

---

## 5. Testing

**Problem:** pytest is configured (`asyncio_mode = auto`) but no test files exist. The two heaviest files (`nodes.py` at ~700 lines, `db.py` at ~500 lines) carry almost all logic with no test coverage.

**Solution:** Add unit tests for computation functions and integration tests for handler pipelines.

**Scope:**
- **Unit tests:** `_compute_slope`, `_compute_pearson`, consistency/streak calculation, intent parameter parsing, markdown-to-HTML conversion
- **Integration tests:** Each handler node with mocked DB responses — verify they produce expected state (response_text, chart_bytes, followups)
- **DB tests:** Key queries against a test database with known seed data (can reuse `db/seed_dummy_data.sql`)
- **Edge case tests:** Empty data, single data point, mismatched metric names, rate limiting

---

## 6. Break Up `nodes.py`

**Problem:** All 10 handler implementations live in a single ~700-line file. Each follows a similar pattern (parse params, query DB, compute, chart, LLM synthesis, return state) but they're all inlined together, making the file hard to navigate and test.

**Solution:** Extract handlers into separate modules or at minimum extract shared patterns.

**Scope:**
- Option A: One file per handler (e.g. `agent/handlers/trend.py`, `agent/handlers/correlation.py`)
- Option B: Extract shared patterns (DB query + chart + LLM synthesis) into a base handler pattern, keep handler-specific logic concise
- Move the two LLM client instances to a shared module rather than creating them at module level in nodes.py

---

## 7. Smarter Weekly Digest

**Problem:** The digest summarizes all active metrics regardless of whether anything interesting happened. A flat week with no changes still produces a wall of text and charts.

**Solution:** Make the digest highlight-driven — focus on what's notable and skip what's boring.

**Scope:**
- Score each metric's "interestingness" for the week (large % change, broken streak, new high/low, anomaly detection)
- Only include detailed summaries + charts for metrics above a threshold
- Add a "nothing notable" summary for quiet metrics (one line, no chart)
- Highlight experiment milestones (started, ended, significant results)
- Include a "heads up" section for declining consistency or broken streaks

---

## 8. Smaller Wins

### Caching
- Cache the active metric list (it changes rarely) to avoid a DB query on every message
- Consider caching recent query results with a short TTL for rapid follow-up questions

### Missing Visualizations
- `streak` intent has no chart — add a calendar heatmap or streak timeline
- `boolean_frequency` has no chart — add a simple pie or bar chart
- `correlation_ranking` has no chart — add a horizontal bar chart of top r-values

### Prompt Grounding
- Several synthesis prompts don't include the actual date range being analyzed, making LLM responses vague about timeframes
- Include explicit dates (e.g. "March 7 - April 5, 2026") in synthesis prompts so the narrative references real dates

### Response Formatting
- Standardize how numbers are presented (consistent decimal places, units where applicable)
- Add sparkline-style Unicode characters for inline trend indicators in text responses
