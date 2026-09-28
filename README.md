# Support Ticket Insights Agent

Ask questions about customer support tickets in plain English. Count/filter questions are answered exactly from the database. Thematic questions are answered from ticket text with cited sources.

Built as a portfolio project using the Anthropic Claude API, FastAPI, Streamlit, and Postgres with pgvector.

---

## What it does

An ops or support lead can ask things like:

- "How many critical-priority tickets are still open?" → exact count from the database, with the SQL shown
- "What are the most common technical issues customers report?" → thematic summary with the ticket excerpts it drew from
- "How many refund requests came in through chat vs email?" → SQL aggregation
- "Summarize what people complain about with GoPro Hero tickets" → RAG retrieval + synthesis

Questions outside the data's scope get an honest "I don't know" rather than a fabricated answer.

---

## Architecture

Two-branch routing:

```
User question
    └─ Router (Claude Haiku) ──► count/filter ──► SQL-gen (Claude Haiku)
                                                       └─► SELECT on tickets_safe (read-only role)
                                                               └─► Answer + SQL shown
                             ──► thematic ────► Embed question
                                                       └─► pgvector similarity search
                                                               └─► RAG summary (Claude Sonnet) + cited tickets
                             ──► out of scope ──► "I don't know"
```

Full diagrams: [docs/architecture.md](docs/architecture.md)
Tech choices and rejected alternatives: [docs/tech-choices.md](docs/tech-choices.md)
Risk analysis and failure modes: [docs/risks-and-safety.md](docs/risks-and-safety.md)

### Key safety properties

- **No mutation possible:** the SQL-gen path connects as a Postgres role that has no write grants and can only `SELECT` on `tickets_safe`. The app layer also rejects non-SELECT statements before executing — both layers independently enforce the same constraint.
- **No PII to the LLM:** `tickets_safe` is a view that excludes all four PII-shaped columns (`customer_name`, `customer_email`, `customer_age`, `customer_gender`). Enforced by the database, not by prompt instructions.
- **Sources always shown:** SQL branch returns the query it ran; RAG branch returns which ticket excerpts it used.

---

## Data

Public synthetic dataset: [Kaggle Customer Support Ticket Dataset](https://www.kaggle.com/datasets/suraj520/customer-support-ticket-dataset) — 8,469 rows, 17 columns.

Key data caveats (full detail in [data-notes.md](data-notes.md)):
- No ticket-created timestamp exists. `date_of_purchase` is when the *product* was bought, not when the ticket was filed.
- `ticket_description` is templated in 100% of rows (`{product_purchased}` placeholder left unresolved). Retrieval leans on structured fields (`ticket_type`, `ticket_subject`, `product_purchased`).
- `resolution` text is 100% unrelated filler — excluded from the RAG corpus.
- `first_response_time`/`time_to_resolution` are independent random timestamps, not a valid duration pair (49% negative deltas). Never used for time-to-resolve calculations.

---

## Project status

| Step | Description | Status |
|------|-------------|--------|
| 1-4 | Problem statement, eval questions, done/good definition, constraints | Done |
| 5-6 | Data exploration, data notes | Done |
| 7 | Clean Postgres schema (`db/schema.sql`) | Done |
| 8 | Architecture diagrams (`docs/architecture.md`) | Done |
| 9 | Tech choices (`docs/tech-choices.md`) | Done |
| 10-11 | Risk analysis, failure modes (`docs/risks-and-safety.md`) | Done |
| 12 | Project skeleton, README | Done (this file) |
| 13 | Data pipeline: clean CSV → Postgres, verify | Done |
| 14 | End-to-end text-to-SQL path (script, no UI) | Done |
| 15 | Eval script, run against text-to-SQL | Done |
| 16 | RAG path + router | Done |
| 17 | FastAPI + Streamlit UI | Done |
| 18 | Deploy + eval on deployed version | **Next** |
| 19 | Handoff README + architecture story | Pending |
| 20 | Retrospective | Pending |

---

## Local setup

**Prerequisites:** Docker, Python 3.11+, an Anthropic API key.

```bash
# 1. Clone and set up environment
git clone <repo>
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

## Repository layout

```
.
├── agent/
│   ├── db.py           # DB connections (sql_gen_readonly + admin)
│   ├── prompts.py      # Router and SQL-gen system prompts
│   ├── router.py       # route(question) → "sql" | "rag" | "unknown"
│   ├── sql_gen.py      # ask_sql() — generate SELECT, validate, run, return rows
│   └── rag.py          # ask_rag() — embed, pgvector search, Sonnet summarization
├── api/
│   └── main.py         # FastAPI app — POST /ask, GET /health
├── ui/
│   └── app.py          # Streamlit chat UI
├── data/
│   ├── raw/            # original Kaggle CSV (not modified)
│   └── clean/          # output of clean_data.py
├── db/
│   ├── schema.sql      # DDL: tickets, tickets_safe view, ticket_embeddings
│   └── roles.sql       # sql_gen_readonly role (SELECT-only on tickets_safe)
├── docs/
│   ├── architecture.md     # Mermaid flow diagrams
│   ├── tech-choices.md     # Component decisions and rejected alternatives
│   └── risks-and-safety.md # Risk ranking and failure mode handling
├── notebooks/
│   └── 01_explore.ipynb    # Step 5 data exploration (executed)
├── scripts/
│   ├── ask.py              # CLI entry point
│   ├── clean_data.py       # Raw CSV → clean CSV with validation
│   ├── embed_tickets.py    # One-time batch: populate ticket_embeddings
│   ├── eval.py             # Eval suite: 17 questions, routing + SQL + RAG checks
│   ├── load_to_postgres.py # Clean CSV → Postgres (idempotent)
│   └── verify_db.py        # Manual DB verification queries
├── data-notes.md       # Step 5/6 findings and cleaning decisions
├── CONTEXT.md          # Full project context and 20-step plan
├── docker-compose.yml  # Postgres 16 + pgvector
├── .env.example        # Copy to .env for local dev
└── requirements.txt    # Python dependencies
```

---

## Known limitations

- **No ticket-created timestamp.** Recency questions ("tickets opened last week") aren't answerable as literally worded. The system returns "I don't know" for these rather than substituting `date_of_purchase`.
- **Shallow RAG signal.** Ticket descriptions are synthetic/templated. Thematic answers reflect ticket type/subject distributions correctly but lack the depth a real corpus would provide.
- **No auth.** This is a portfolio demo. A real deployment would add authentication before exposing any ticket data.
- **No conversation memory.** Each question is answered independently; follow-up questions don't refer to prior context.
- **`ticket_embeddings` table is empty** until Step 16 (RAG path) is built and the embedding model runs the one-time batch.
