# Support Ticket AI System

An AI-powered system over a customer support ticket dataset. It ingests raw
ticket data into a queryable store, answers natural-language questions about
it via an LLM-backed SQL agent, flags operational anomalies with
deterministic Python, and exposes both through a REST API and a Streamlit
UI.

## Setup

### Option A: Docker (recommended)

```bash
git clone (https://github.com/snehitsharma/support-ticket-ai-system)
cd support-ticket-ai-system

cp .env.example .env          # then edit .env and set GROQ_API_KEY
# Groq free tier: https://console.groq.com

# Place the dataset at data/support_tickets.csv (already included in this repo)

docker compose up -d --build
```

- API: `http://localhost:1234` (Swagger docs at `http://localhost:1234/docs`)
- UI: `http://localhost:1456`

`docker compose down` to stop. `tickets.db` is rebuilt fresh from the CSV on
every container start, so no volume/persistence step is needed.

### Option B: Local Python

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS/Linux

pip install -r requirements.txt

cp .env.example .env          # then edit .env and set GROQ_API_KEY

uvicorn main:app --reload --port 1234
```

The app ingests `data/support_tickets.csv` into `tickets.db` automatically
on startup (`main.py`'s `lifespan`), no manual ingestion step. API docs at
`http://127.0.0.1:1234/docs`.

To run the UI (separate terminal, API must already be running):

```bash
streamlit run ui.py --server.port 1456
```

## Architecture

```
data/support_tickets.csv
        │  ingestion/ingest.py (extract → transform → load)
        ▼
    tickets.db (SQLite, read-only connection)
        │                                   │
        │ NL question                       │ direct pandas read
        ▼                                   ▼
  query.py: guardrail → LangChain      anomalies.py: stale-ticket
  SQL agent (Groq LLM) → SQL → answer  filter + per-category z-score
        │                                   │
        └───────────────┬───────────────────┘
                         ▼
                    FastAPI (main.py)
                    /query  /anomalies  /health
                         │
                         ▼
                  Streamlit UI (ui.py)
```

**Storage: SQLite, not Postgres/DuckDB.** Zero-config single-file DB, no
Docker/service dependency to even boot (Docker here is for convenience, not
a hard requirement, Option B runs with just `pip install`). 500 rows on one
evaluator session is nowhere near the scale where Postgres's complexity pays
for itself. Trade-off: would move to Postgres and continuous ingestion if
this became a live multi-writer service.

**No vector DB, no RAG retrieval step.** The sample queries are structured
aggregation/filter queries (COUNT, GROUP BY, AVG, WHERE), not semantic
similarity search. The full 10-column schema is small enough to inject into
every prompt directly (`prompts/schema_context.py`), rather than retrieved
per-query. At this scale, retrieval would add complexity without benefit.

**NL-to-SQL via a LangChain SQL agent** (`create_sql_agent`, tool-calling
agent type), not a one-shot chain. This gives retry/self-correction when the
first generated SQL is malformed, since the agent can inspect the error and
try again rather than just failing.

**Read-only guardrail is connection-level, not prompt-level.** `db.py` opens
SQLite via `sqlite3.connect(f"file:{path}?mode=ro", uri=True)`, OS/DB
enforced, so even a hallucinated `DROP`/`DELETE` fails at the connection
layer regardless of what the LLM generates, no matter how the prompt is
worded. No write/mutation capability exists anywhere in the system.

**Input/output scope guardrail is two-layered, on purpose.** `check_guardrail()`
in `query.py` does a cheap, deterministic keyword check before any LLM call.
It rejects obviously-mutating phrasing and questions with zero
table-related vocabulary, so an off-topic question never pays for agent
construction or a Groq round-trip. On top of that, `AGENT_BEHAVIOR_PROMPT`
instructs the agent to answer only the on-topic part of a mixed question and
refuse the rest. This second layer is prompt-based and therefore
best-effort, not a hard guarantee (see Known Limitations, and What I'd
Improve).

**Anomaly detection is deterministic Python, not LLM-based** (`anomalies.py`).
It's pure stats/filtering, an LLM round-trip would be slower, costlier, and
less reliable for zero benefit. Only NL query answering uses the LLM.
- *Unresolved high-priority tickets older than 24h*: `status != 'Resolved'
  AND priority IN ('High','Critical') AND (now - created_at) > 24h`.
- *Abnormally long resolution times*: chose **per-category z-score**
  (`resolution_time_hrs > mean + 2*std`, computed separately per `category`)
  over a global cutoff, because categories have genuinely different
  resolution-time distributions (Technical tickets legitimately take longer
  than General ones). A single global threshold would either over-flag
  Technical or under-flag General.

**Column disambiguation**: `response_time_hrs` (time to first response) vs.
`resolution_time_hrs` (time to resolution) are easy for an LLM to confuse
from names alone, both are separated out clearly in `COLUMN_DESCRIPTIONS`
(`prompts/schema_context.py`). `customer_rating` and `resolution_time_hrs`
being `NULL` means "unresolved," not zero, also called out there so the
agent excludes NULLs from averages rather than treating them as 0 (verified:
Technical category average is 3.74 excluding NULLs vs. 2.56 if NULLs were
treated as 0).

**Date-format bug caught and fixed during testing.** `created_at` in the
real data is `YYYY-MM-DD HH:MM` (e.g. `2024-02-05 11:14`), but an earlier
version of `transform()` parsed with `format="%m/%d/%Y %H:%M"`. Every row
silently became `NULL`, which made the stale-ticket anomaly check return an
empty list (a false "no anomalies," not a real one). Caught by manually
sanity-checking the anomaly counts against a raw pandas filter. Fixed by
parsing with the correct `"%Y-%m-%d %H:%M"` format.

**Project layout**, one concern per file:
- `prompts/schema_context.py`: `COLUMN_DESCRIPTIONS` dict + `format_for_prompt()`.
- `db.py`: read-only SQLite connection logic only.
- `llm/models.py`: `get_llm()`, the Groq client construction only.
- `query.py`: guardrail, agent behavior prompt, agent construction, `answer_query()`.
- `ingestion/ingest.py`: `extract()` / `transform()` / `load()` / `run_ingestion()`.
- `anomalies.py`: the two anomaly checks + `detect_anomalies()`.
- `main.py`: FastAPI routes only.
- `ui.py`: Streamlit UI only.
- `mcp_server/`: optional bonus MCP server (see the note at the bottom).

## Model / Tools Used

- **Groq, `openai/gpt-oss-120b`**, `temperature=0`. Originally built against
  `llama-3.3-70b-versatile`. `gpt-oss-120b` was the largest active model on
  the key that still supports tool-calling (required by `create_sql_agent`'s
  `tool-calling` agent type).
- **LangChain SQL agent** (`langchain-community`): NL-to-SQL with
  self-correction, over a hand-rolled single-shot prompt-to-SQL pipeline.
- **FastAPI**: async lifespan hook for one-time ingestion at startup, free
  OpenAPI/Swagger docs.
- **Streamlit**: fastest path to a usable UI for a two-tab, form-driven app,
  not worth a JS frontend at this scope.
- **SQLite**: see Architecture.
- **Pydantic**: FastAPI request/response models (`QueryRequest`/`QueryResponse`).

## Example Queries & Outputs

All captured from real runs against the live 500-row dataset (via
`python query.py` / `POST /query`), not fabricated.

```
Q: How many tickets are currently open?
A: There are 111 tickets that are currently open.

Q: Which agent has the lowest average customer rating?
A: The agent with the lowest average customer rating is AGT-08,
   with an average rating of 3.48.

Q: What is the average customer rating for Technical category tickets?
A: The average customer rating for tickets in the Technical category
   is 3.74.

Q: Which agent resolved the most tickets this month?
A: No tickets were marked Resolved during the current month, so there
   isn't an agent who resolved the most tickets this month.
   (Correct: the dataset only spans Jan-Apr 2024, "this month" is
   evaluated against the real current date, which has zero overlap.)

Q: Show me all Critical tickets not resolved within 12 hours
A: [34-row table], e.g. TKT-238 (53.4h), TKT-255 (66.6h), TKT-446
   (60.6h) plus 31 still-unresolved Critical tickets. Cross-checked
   against a raw pandas filter: 55 total Critical tickets, 34 not
   resolved within 12h, matches exactly.
```

`GET /anomalies` (live output, truncated):

```json
{
  "stale_high_priority": [
    {"ticket_id": "TKT-007", "reason": "High priority, status=Open, open for 23270.9h (> 24h threshold)"},
    {"ticket_id": "TKT-060", "reason": "Critical priority, status=Escalated, open for 22337.5h (> 24h threshold)"}
    // ... 80 total
  ],
  "long_resolution_times": [
    {"ticket_id": "TKT-023", "reason": "resolution_time_hrs=76.1h in category 'Billing' (mean=16.3h, std=16.0h, z=3.73, threshold=48.4h)"},
    {"ticket_id": "TKT-092", "reason": "resolution_time_hrs=84.2h in category 'Technical' (mean=20.6h, std=20.4h, z=3.12, threshold=61.3h)"}
    // ... 17 total
  ]
}
```

## Known Limitations

- **The off-topic/scope refusal is prompt-based, hence probabilistic.**
  Tested with several mixed questions (e.g. "how many tickets are pending,
  and what is the capital of France?"): compliant on most runs, but on
  repeated identical calls it sometimes answered the off-topic part anyway,
  and once produced an unfilled `[pending_count]`-style placeholder instead
  of running the actual query. There is no code-level guarantee here, only
  `check_guardrail()`'s upfront keyword check is deterministic.
- **The word "pending" was answered inconsistently across calls.** One run
  scoped it to `status = 'Open'` (111), another to `status != 'Resolved'`
  (173, including Escalated). Expected LLM SQL-generation ambiguity on
  vague aggregation scope, not a bug to "fix" so much as a reminder that
  phrasing matters.
- **No caching of the SQL agent, roughly 7-8s per query.** `answer_query()`
  rebuilds `create_engine`/`SQLDatabase`/`create_sql_agent` from scratch on
  every call. Measured breakdown: ~4.3s agent construction + ~2.6s actual
  LLM round-trips (schema lookup, generate SQL, execute, synthesize answer).
  Caching a single agent instance (e.g. built once at FastAPI startup) would
  roughly halve this.
- **No schema/row-level validation on ingestion.** `extract()` reads the CSV
  as-is with no column-presence check and no per-row Pydantic validation,
  bad values are silently coerced to `NULL` via `pd.to_numeric(errors="coerce")`.
  Deliberately simplified, deferred as a v2 hardening step, not needed for
  this fixed, known-good dataset.
- **No test suite, evals, or observability.** No automated regression tests
  (the date-format bug above was caught by manual inspection, not a test),
  no logging/tracing of agent steps, token usage, or latency in production.
- **No vector DB / retrieval**, deliberately out of scope. See Architecture.
- **MCP server (`mcp_server/`) is a bonus, not integration-tested end-to-end
  with a real MCP client**, and not included in the Docker Compose stack. It
  runs over stdio, which doesn't map cleanly onto a persistent networked
  container the way the FastAPI/Streamlit services do.
- **No write/mutation capability anywhere**, out of scope by design. The
  system is read-only end to end.

## What I'd Improve With More Time

Priority order:

1. **A deterministic output guardrail.** Right now only the *input* side has
   a hard, code-level check (`check_guardrail()`'s keyword scan before any
   LLM call runs). The scope refusal for mixed questions lives entirely in
   the prompt, which is why it leaks sometimes (see Known Limitations). The
   fix is to also check the agent's *final answer* deterministically before
   it's returned, not just the question going in.
2. **Sanitize around the existing input guardrail**, since it stays
   prompt-assisted/probabilistic on the "is this actually about the ticket
   data" judgment call (a pure keyword list can't fully capture intent).
   Strip/normalize the question (collapse whitespace, cap length, drop
   obvious prompt-injection patterns like "ignore previous instructions")
   before it ever reaches the LLM, so the probabilistic layer is working
   with a cleaner, smaller attack surface.
3. **Cache/reuse the SQL agent** across requests instead of rebuilding it
   per call, to cut the ~4.3s construction overhead out of every query.

Also worth doing:

- **A small eval set** of the manually-verified queries in this README
  (with known-correct answers) run automatically on every change, so a
  future regression like the `created_at` format bug gets caught by CI
  instead of by hand.
- **Basic observability**: structured logging of generated SQL, latency,
  and token usage per query, at minimum for debugging agent behavior.
- **Postgres and continuous/incremental ingestion** if this ever became a
  live multi-writer service instead of a static evaluation dataset.
- **Retrieval-based schema context** if the system grew to multiple tables.
  Injecting the full schema into every prompt stops scaling once it's more
  than a handful of tables.

---

**Side note on `mcp_server/`.** Right now it's a thin wrapper: two tools
(`get_schema`, `query_tickets`) over this one specific database, running
over stdio for a local MCP client. But the general shape of it, read-only
SQL access plus a schema-description tool, isn't really tied to this
dataset. If a one-time LLM-assisted labeling step were added (having a
model generate the `COLUMN_DESCRIPTIONS`-style semantic annotations for an
arbitrary table on first connection, instead of hand-writing them like
`prompts/schema_context.py` does here), this pattern generalizes into an MCP
server that can point at *any* SQLite/Postgres DB and let Claude or GPT
query it conversationally, without a human writing schema docs for every
new database up front. Not built here, just a natural next step this
project's shape points toward.
