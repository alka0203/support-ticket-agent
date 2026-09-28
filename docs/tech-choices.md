# Tech Choices (Step 9)

Decisions and rejected alternatives for each component.

---

## LLM: Anthropic Claude API

**Router call:** `claude-haiku-4-5` — classification only (SQL vs RAG vs out-of-scope).
Fast and cheap (~$0.0008/1K input tokens). The task is narrow and well-structured: three
possible labels, a short system prompt with clear criteria. A stronger model adds latency
and cost without measurably improving a binary/ternary classification decision.

**SQL-gen call:** `claude-haiku-4-5` — generate a single SELECT statement against a known
schema. The system prompt is the real forcing function (schema, ENUM values, known data
caveats). Haiku handles this reliably; escalate to Sonnet if eval accuracy is poor.

**RAG summarization call:** `claude-sonnet-4-6` — thematic synthesis is where answer quality
is most visible to a human reviewer. One call per query, not per chunk, so the cost is
bounded even with the stronger model.

**Rejected alternatives:**
- *OpenAI GPT-4o / GPT-4o-mini:* this is an Anthropic portfolio piece; using Anthropic's
  own SDK is consistent and demonstrates the API.
- *Local Llama (Ollama):* slow inference on a free-tier deploy target, non-trivial memory
  overhead, not needed at 8,469 rows.
- *Single LLM call for all three jobs:* one prompt trying to classify + generate SQL or
  summarize RAG results simultaneously increases prompt complexity, mixes concerns, and
  makes eval harder (can't isolate which step failed).

---

## Embeddings: sentence-transformers `all-MiniLM-L6-v2`

384-dimensional vectors. Runs locally (no API call, no per-embedding cost). Fast enough for
a one-time offline batch of 8,469 rows. 384 dims is already baked into `db/schema.sql`'s
`VECTOR(384)` column.

**Rejected alternatives:**
- *OpenAI text-embedding-3-small:* costs money per embedding, adds an external API
  dependency for a one-time offline step, and the signal quality difference is irrelevant
  given that `Ticket Description` is 100% templated filler (per `data-notes.md`).
  Retrieval quality is bounded by data quality, not model choice.
- *all-mpnet-base-v2:* 768 dims. Would require changing the schema VECTOR dimension
  and re-running all migrations. No quality gain worth that churn at this data scale.

---

## API: FastAPI

Async, lightweight, auto-generated OpenAPI docs at `/docs`. The `/ask` endpoint receives a
question and returns a structured JSON response (answer + source type + sources). Pydantic
models for request/response validation.

**Rejected alternatives:**
- *Flask:* no native async support; would need a WSGI adapter for any async LLM call
  handling.
- *Django REST Framework:* heavyweight for a single endpoint; adds ORM, admin, migrations
  machinery that conflicts with the manual Postgres+schema approach already chosen.

---

## UI: Streamlit

Single-page chat-style interface. Deployable to Streamlit Community Cloud on the free tier
with a public URL — right for a portfolio demo. Minimal JS/HTML, fast to iterate.

**Rejected alternatives:**
- *React/Next.js:* appropriate production choice, wrong for a portfolio demo where speed of
  build and zero-cost hosting matter more than frontend flexibility.
- *Gradio:* similar effort to Streamlit, less control over layout, more ML-demo-flavored
  than a "real app" aesthetic.

---

## Database: Postgres 16 + pgvector (Docker Compose)

Already built (Step 13). pgvector HNSW index for cosine similarity search over embeddings.
Single container, persistent volume. The `sql_gen_readonly` role enforces SELECT-only access
to `tickets_safe` at the DB level.

**Rejected alternatives:**
- *SQLite:* no pgvector support, no role/permission system — the two DB-level guardrails
  (read-only, PII-free view) would need to move entirely into application code.
- *Pinecone/Weaviate (managed vector DB):* external API dependency, cost, overkill for
  8,469 rows. Keeping vectors in Postgres means one fewer service to deploy and one fewer
  failure point.
- *ChromaDB:* no SQL — would need a separate SQL database alongside it, splitting the data
  across two systems for no benefit at this scale.

---

## Deployment target: Render (API) + Streamlit Community Cloud (UI)

Both have free tiers. Render can run a Docker-backed FastAPI + Postgres service; Streamlit
Community Cloud deploys directly from a GitHub repo. Both support environment variable
injection for the API key and DB credentials.

**Note:** deployment is Step 18; this section documents the *decision*, not the execution.

---

## Python dependency management: pip + requirements.txt

Simple, universally understood, zero tooling overhead. This is a portfolio project with one
developer. A lock file (`pip freeze`) is available if exact reproducibility is needed.

**Rejected alternatives:**
- *Poetry / uv:* correct choice for a team or long-lived project; added tooling complexity
  not justified here.
- *conda:* heavier than needed; no conda-specific packages in this stack.
