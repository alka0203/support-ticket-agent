# Risks and Safety (Steps 10-11)

## Step 10 — Riskiest parts, tested first

Ranked by "most likely to sink the project if it doesn't work."

### Risk 1: Routing misclassification (highest)

If the router sends a count/filter question to the RAG branch, the user gets a vague
thematic summary instead of an exact number — confidently wrong. If it sends a thematic
question to the SQL branch, SQL-gen produces nonsense or a low-confidence query.

**Mitigation:** the eval set (Step 15) is specifically split into SQL questions (10),
RAG questions (5), and mixed/stress-test questions (2). Routing accuracy is measured
explicitly before any other metric. Target: 100% on the 10 pure SQL and 5 pure RAG
questions before moving to the mixed ones.

**Test-first approach:** write a routing-only test (no SQL execution, no RAG retrieval)
that sends each of the 17 eval questions through the router call and checks the label.
Run this immediately after Step 14's first working end-to-end path.

### Risk 2: SQL hallucination / wrong ENUM values (high)

The SQL-gen call could produce queries referencing column names that don't exist, ENUM
values spelled incorrectly, or joins against tables the read-only role can't see. These
fail loudly (Postgres errors, not silent wrong answers) — but a loud error is still a
failed answer.

**Mitigation:** the system prompt for SQL-gen includes the full `tickets_safe` schema,
all ENUM values verbatim, and explicit "never use these columns" callouts for the
timestamp-duration caveats from `data-notes.md`. Postgres ENUMs enforce loud failure on
invalid values, so hallucinated categories produce a clear error rather than a "0 rows"
answer. The eval script (Step 15) counts Postgres errors separately from wrong answers.

### Risk 3: RAG retrieval quality on low-signal data (medium)

`Ticket Description` is 100% templated filler; `Resolution` is 100% noise. Embedding
quality is bounded by the text, not the model. A semantic search over noise returns
noise-adjacent neighbors.

**Mitigation (already decided in data-notes.md):** `retrieval_text` is built from
`ticket_type + ticket_subject + product_purchased` as primary signal, with
`ticket_description` as supplementary context. The RAG summarization prompt instructs
the model to lean on the structured fields and flag when description text looks like
template noise. Eval questions 11-15 use human-graded "reasonable + sourced" criteria,
not exact match, so partial signal still passes.

**Accepted residual risk:** thematic questions like "what do customers complain about
for [product]?" will return structurally correct answers (correct ticket type/subject
breakdown) but shallow thematic depth. This is documented as a known limitation in
Step 19.

### Risk 4: Cost overrun from LLM API calls during development (low-medium)

The eval set is 17 questions; an eval run costs ~17 LLM calls (router) + up to 17
(SQL-gen or RAG-gen). At Haiku pricing, negligible. The risk is accidentally running
the eval in a loop or against all 8,469 tickets instead of the 17-question set.

**Mitigation:** hard spend cap on the API key. Eval script accepts `--dry-run` flag
(Step 15) that prints what it would send without making API calls.

### Risk 5: Deployment environment difference breaks local behavior (low)

Postgres connection strings, environment variables, or the read-only role behavior may
differ between local Docker Compose and Render.

**Mitigation:** the eval script (Step 15) runs against the deployed version after
Step 18, using the same 17 questions. Any regression is caught before the handoff.

---

## Step 11 — Failure modes and safety

### Bad SQL (mutation attempt)

**Scenario:** SQL-gen produces a DELETE, UPDATE, INSERT, or DROP.

**Double-enforced prevention:**
1. `sql_gen_readonly` Postgres role has no write grants — the statement fails at the DB
   level with a permission error.
2. Application layer (FastAPI `/ask` handler) parses the generated SQL before execution
   and refuses to run any statement that doesn't start with SELECT (after stripping
   comments and whitespace). Either layer alone is sufficient; both together mean a bug
   in one doesn't expose the other.

**Failure output:** structured error response to the user — "I generated SQL but it was
not a SELECT statement and was not run." The generated SQL is logged for inspection.

### Unanswerable / out-of-scope questions

**Scenario:** "How many tickets were filed last Tuesday?" (no ticket-creation timestamp),
or "What's the CEO's email?" (completely out of scope).

**Prevention:** router has an explicit third branch — "out of scope / unanswerable" —
that returns a canned "I don't know / this isn't in the data" response rather than
forcing the question into the nearest-fitting handler and guessing.

**Failure output:** "I don't know" with a brief reason where possible ("this dataset
doesn't include a ticket-filed date, only a product purchase date").

### API / LLM call timeout or error

**Scenario:** Anthropic API returns a 5xx, network timeout, or rate-limit error.

**Prevention:** FastAPI endpoint catches `anthropic.APIError` and returns a 503 with a
clear message. No retry loop that could multiply cost; the user retries manually if
they choose.

### Retrieval returns zero results

**Scenario:** pgvector similarity search returns nothing above the cosine similarity
threshold.

**Prevention:** no hard threshold — return the top-k neighbors regardless of score, but
include the similarity scores in the response. The RAG summarization prompt is told to
say "I found only weakly-related tickets" if scores are low, rather than fabricating a
confident answer from noise.

### SQL query returns zero rows (valid query, empty result)

**Scenario:** "How many critical-priority tickets are open?" — the query runs cleanly
but returns 0.

**Behavior:** this is a valid answer, not a failure. The response returns "0" with the
SQL that was run, so the user can verify the query logic. The system never substitutes
"no results" with a guess.

### Docker / Postgres unavailable locally

**Scenario:** developer runs the app without starting Docker Compose.

**Prevention:** FastAPI startup checks the DB connection and exits with a clear error
message if it can't connect, rather than starting and failing on the first query.
`docker-compose up -d` is step one in the README setup instructions.
