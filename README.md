# Support Ticket Insights Agent

Ask questions about customer support tickets in plain English. Count/filter questions are answered exactly from the database with the SQL shown. Thematic questions are answered from ticket text with cited sources. Questions outside the data's scope get an honest "I don't know."

Built as a portfolio project using the Anthropic Claude API, FastAPI, Streamlit, and Postgres with pgvector.

**Live demo:** https://support-ticketing-agent.streamlit.app

---

## The problem

Ops and support leads currently have to manually scan thousands of tickets to spot volume trends, priority backlogs, and recurring complaint themes. This agent lets them ask in plain English — and get a trustworthy answer in seconds instead of hours of manual digging.

Example questions it handles:

| Question | Type | Answer |
|---|---|---|
| How many critical-priority tickets are still open? | SQL | 692 |
| Which products have the most technical-issue tickets? | SQL | GoPro Hero (57), Amazon Echo (48)… |
| What are the most common technical issues customers report? | RAG | Summary + 15 cited tickets |
| Summarize why customers request refunds | RAG | Summary + 15 cited tickets |
| Which tickets are open after 3 days? | Edge | "I don't know — no valid duration in this data" |

---

## Architecture

A router classifies each question and dispatches it to one of two specialized handlers — not one LLM doing everything. This was chosen over a single-agent approach because the task structure is known and repeatable, and reliability matters more than open-ended adaptability.

```
User question
    └─ Router (Claude Haiku) ──► count/filter ──► SQL-gen (Claude Haiku)
                                                       └─► SELECT on tickets_safe (read-only role)
                                                               └─► Answer + SQL shown
                             ──► thematic ────► Embed question (all-MiniLM-L6-v2)
                                                       └─► pgvector similarity search
                                                               └─► Summarize (Claude Sonnet) + cited tickets
                             ──► out of scope ──► "I don't know"
```

Full Mermaid diagrams: [docs/architecture.md](docs/architecture.md)

### Safety properties — enforced at the database, not in prompts

The most interesting part of the design is where the guardrails live:

- **No mutation possible:** the SQL-gen path connects as a Postgres role (`sql_gen_readonly`) with no write grants. The app layer *also* rejects non-SELECT statements before executing. Either layer alone is sufficient; both together mean a prompt injection or LLM bug in one layer doesn't remove the other.
- **No PII to the LLM:** `tickets_safe` is a Postgres view that excludes all four PII-shaped columns (`customer_name`, `customer_email`, `customer_age`, `customer_gender`). Even if the LLM tried to `SELECT customer_name`, the column doesn't exist in the role's accessible view — the constraint is enforced by the database, not by trusting the system prompt. An earlier version of this view only dropped name/email; an independent audit caught that age/gender were still exposed and it was fixed.
- **No fabricated answers:** the router has an explicit third branch ("out of scope") rather than forcing every question into the nearest-fitting handler and guessing.
- **Sources always shown:** SQL branch returns the exact query that ran; RAG branch returns which ticket excerpts were used.

---

## Eval results

17 representative questions covering all cases: count/filter (SQL), thematic (RAG), edge cases, and a compound question that tests the router under mixed intent.

| Metric | Score | Notes |
|---|---|---|
| Routing accuracy | 16/16 (100%) | Q16 correctly refused as "unknown" — no valid duration in data |
| SQL accuracy | 11/11 (100%) | Exact scalar match + correct row count for aggregations |
| RAG smoke tests | 5/5 (100%) | Non-empty answer, 15 cited sources, no errors |
| Q17 (compound) | No crash | Routed to SQL; partial answer acceptable for this edge case |

The SQL eval compares the agent's result against a reference query for each question. Scalar results are compared numerically (rounding to 2dp for float averages); multi-row results check row count only — column alias differences (`count` vs `ticket_count`) don't count as failures.

Run it yourself:
```bash
python scripts/eval.py
```

---

## Design decisions and tradeoffs

**Why a router, not a single LLM call?**
One LLM call doing both classification and generation (SQL or summary) in a single prompt mixes two different jobs with different requirements, makes failures harder to diagnose, and forces a tradeoff between the concise prompt needed for routing and the detailed schema context needed for SQL-gen. Splitting into router → specialized handler makes each prompt purpose-built and each failure point independently testable.

**Why Claude Haiku for routing and SQL-gen, Sonnet for RAG?**
Haiku is fast and cheap (~$0.0008/1K input tokens) and handles both ternary classification and single-table SQL generation reliably with a strong system prompt. Sonnet is reserved for the RAG summarization step where quality is visible to a human reviewer — and at one call per query (not per ticket), the cost is bounded.

**Why `all-MiniLM-L6-v2` for embeddings?**
It runs locally (no API cost, no external dependency), it's fast enough for a one-time batch of 8,469 rows (~10s on CPU), and its 384-dimension vectors fit the schema already defined. OpenAI's `text-embedding-3-small` would add API cost for a one-time offline step with no meaningful quality gain — RAG quality here is bounded by data quality, not model choice.

**Why the RAG answers are intentionally shallow**
`ticket_description` is templated in 100% of rows (the `{product_purchased}` placeholder was never substituted, and random Faker sentences follow). `resolution` is 100% unrelated filler. Retrieval is built primarily over `ticket_type + ticket_subject + product_purchased`, which carry real signal. The RAG answers correctly reflect the *structural* distribution of complaints (by type and subject) but can't provide the semantic depth a real corpus would give. This is documented as a known limitation rather than hidden.

**Why Postgres over a dedicated vector database?**
At 8,469 rows, a dedicated vector DB (Pinecone, Weaviate) would add an external service dependency for no performance benefit. Keeping vectors in Postgres with pgvector means one data store, one set of backups, and the ability to join embeddings with structured ticket fields in a single query — which the RAG retrieval does.

---

## Data

Public synthetic dataset: [Kaggle Customer Support Ticket Dataset](https://www.kaggle.com/datasets/suraj520/customer-support-ticket-dataset) — 8,469 rows, 17 columns.

Key caveats (full detail in [data-notes.md](data-notes.md)):
- No ticket-created/filed timestamp exists — only `date_of_purchase` (product purchase, not ticket). The system refuses "tickets opened last week" style questions rather than substituting the wrong date.
- `ticket_description` is templated in 100% of rows. Retrieval leans on structured fields.
- `resolution` text is 100% random filler — excluded from the RAG corpus entirely.
- `first_response_time`/`time_to_resolution` are independent random timestamps with 49% negative deltas — never used for duration calculations.

---

## Local setup

**Prerequisites:** Docker, Python 3.11+, an Anthropic API key.

```bash
# 1. Clone and set up environment
git clone https://github.com/alka0203/support-ticket-agent
cd support-ticket-agent
cp .env.example .env
# Edit .env: set POSTGRES_PASSWORD, SQL_GEN_DB_PASSWORD, ANTHROPIC_API_KEY

# 2. Create virtualenv and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Start Postgres
docker compose up -d

# 4. Run the data pipeline (idempotent — safe to re-run)
python scripts/clean_data.py        # raw CSV → data/clean/tickets_clean.csv
python scripts/load_to_postgres.py  # CSV → Postgres (drops/recreates schema each run)

# 5. Generate embeddings (one-time, ~10 seconds)
python scripts/embed_tickets.py

# 6. Start the API (keep this terminal open)
uvicorn api.main:app --port 8000

# 7. In a second terminal (venv active), start the UI
streamlit run ui/app.py
# Opens at http://localhost:8501
```

**CLI (no UI needed):**
```bash
python scripts/ask.py "How many open tickets are there?"
python scripts/ask.py "What are the most common technical issues?"
```

**Run the eval suite:**
```bash
python scripts/eval.py
```

---

## Deployment (Render + Streamlit Community Cloud)

### API on Render

1. In [Render](https://render.com), create a new **Blueprint** and point it at this repo — `render.yaml` defines both the web service and the Postgres database.
2. Set these environment variables in the Render dashboard:
   - `ANTHROPIC_API_KEY` — your Anthropic key
   - `SQL_GEN_DB_PASSWORD` — any strong password (e.g. `openssl rand -hex 16`)
   - `DATABASE_URL` is injected automatically by Render from the linked database.
3. After the first deploy, open the **Render shell** and run the one-time setup:
   ```bash
   python scripts/setup_deploy.py
   ```
   This loads the schema, creates the `sql_gen_readonly` role, loads 8,469 tickets, and generates embeddings (~2 min on the free tier).

> **Free tier note:** the web service sleeps after 15 min of inactivity; first request after sleep takes ~30s. The first RAG request after a cold start also downloads the embedding model (~90MB).

### UI on Streamlit Community Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io) and connect this repo.
2. Set **Main file path** to `ui/app.py`.
3. Under **Advanced settings → Secrets**, add:
   ```toml
   API_URL = "https://support-ticket-agent-api.onrender.com"
   ```

---

## Repository layout

```
.
├── agent/
│   ├── db.py           # DB connections — supports DATABASE_URL (Render) or POSTGRES_* vars
│   ├── prompts.py      # Router and SQL-gen system prompts (schema + ENUM values + data caveats baked in)
│   ├── router.py       # route(question) → "sql" | "rag" | "unknown"
│   ├── sql_gen.py      # ask_sql() — generate SELECT, validate it's a SELECT, run, return rows
│   └── rag.py          # ask_rag() — embed question, pgvector search, Sonnet summarization
├── api/
│   └── main.py         # FastAPI — POST /ask, GET /health, DB liveness check on startup
├── ui/
│   └── app.py          # Streamlit chat UI — answer + SQL/sources in expandable sections
├── data/
│   ├── raw/            # Original Kaggle CSV (not modified)
│   └── clean/          # Output of clean_data.py
├── db/
│   ├── schema.sql      # DDL: tickets, tickets_safe view, ticket_embeddings, 4 ENUM types
│   └── roles.sql       # sql_gen_readonly role — SELECT on tickets_safe only
├── docs/
│   ├── architecture.md      # Mermaid flow diagrams (offline pipeline + online query)
│   ├── tech-choices.md      # Component decisions and rejected alternatives
│   └── risks-and-safety.md  # Risk ranking and failure mode handling
├── notebooks/
│   └── 01_explore.ipynb     # Data exploration (executed)
├── scripts/
│   ├── ask.py               # CLI entry point
│   ├── clean_data.py        # Raw CSV → clean CSV with 11 built-in self-checks
│   ├── embed_tickets.py     # One-time batch: populate ticket_embeddings
│   ├── eval.py              # 17-question eval suite
│   ├── load_to_postgres.py  # Clean CSV → Postgres (idempotent)
│   ├── setup_deploy.py      # One-shot setup for fresh deployments
│   └── verify_db.py         # Manual DB verification queries
├── data-notes.md       # Data exploration findings and all cleaning decisions with rationale
├── render.yaml         # Render Blueprint (web service + Postgres)
├── docker-compose.yml  # Local Postgres 16 + pgvector
├── .env.example        # Copy to .env for local dev
└── requirements.txt    # Python dependencies (top-level only)
```

---

## Known limitations

- **No ticket-created timestamp.** Recency questions ("tickets opened last week") are refused with an explanation rather than answered with the wrong date. This is intentional.
- **Shallow RAG signal.** Ticket descriptions are synthetic/templated with no real semantic content. Thematic answers correctly reflect ticket type and subject distributions but can't provide the depth a real corpus would give. See [data-notes.md](data-notes.md).
- **No auth.** Portfolio demo — a real deployment would add authentication before exposing ticket data.
- **No conversation memory.** Each question is stateless; follow-up questions ("and what about critical ones?") don't refer to prior context.
- **Render free tier cold starts.** The web service sleeps after 15 min; the first RAG request on a fresh start downloads the embedding model (~90MB, ~30s).

---

## Next steps

If this were a real production system, the most valuable things to add next would be:

1. **Real data.** The biggest bottleneck on RAG quality is data quality. With a real ticket corpus where descriptions are actual customer-written text, retrieval would be meaningfully better.
2. **Conversation memory.** Follow-up questions ("how many of those are critical?") require maintaining context across turns. LangChain's conversation memory or a simple chat history in the API session would handle this.
3. **Compound question handling.** Q17 ("how many GoPro Hero tickets, and what are they mostly about?") currently routes to one branch or the other. A proper compound handler would split it, run both, and combine the answers.
4. **Auth + multi-tenancy.** For a real ops team, access control per team/user and audit logging of all queries run.
5. **Streaming responses.** Long RAG summaries feel slow without streaming. FastAPI + Streamlit both support server-sent events.
