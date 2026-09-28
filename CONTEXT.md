# Support Ticket Insights Agent — Project Context

## Status
Steps 1-7 and 13 done (13 done ahead of 8-12 at user's request). Now backfilling 8-11. Step 8 done (below). Next: Step 9 (tech choices + rejected alternatives).

## High-level flow (Step 8 — done)
Two Mermaid diagrams in `docs/architecture.md`: the offline data pipeline (built, Step 13)
and the online query flow (router → text-to-SQL / RAG, not built yet — Steps 14-17). Also
documents *where* each Step 3/4/11 guardrail lives in the diagram (DB-level PII exclusion,
double-enforced SELECT-only, explicit third "I don't know" router path, sources always
returned).

## Data pipeline (Step 13 — done, partial)
- `scripts/clean_data.py`: raw CSV → `data/clean/tickets_clean.csv`. Implements every decision in `data-notes.md` (column rename, ENUM-matching value remap via explicit maps that fail loudly on an unmapped value, no imputation of structurally-missing fields, no synthesized ticket-opened date, `retrieval_text` built only from signal-bearing fields). Has 11 built-in self-checks against the exact numbers in `data-notes.md`; all pass.
- `docker-compose.yml` + `.env.example`: Postgres 16 + pgvector, local dev only.
- `db/roles.sql`: `sql_gen_readonly` role, `SELECT`-only on `tickets_safe`, nothing else — the DB-level enforcement of the no-PII and no-mutation guardrails decided in Step 3/4/7.
- `scripts/load_to_postgres.py`: applies `db/schema.sql` + `db/roles.sql`, loads the cleaned CSV via `pandas.to_sql`. Idempotent (drops/recreates on each run).
- `scripts/verify_db.py`: manual verification queries. All passed: row count and status breakdown match `data-notes.md` exactly; an invalid ENUM value errors instead of silently matching 0 rows; `tickets_safe` confirmed to exclude `customer_name`/`customer_email`; `sql_gen_readonly` confirmed able to read `tickets_safe` but blocked from the base `tickets` table and blocked from any mutation (`DELETE` on `tickets_safe` → permission denied).
- **Not yet done:** `ticket_embeddings` table exists in the schema but is empty — populating it needs an embedding model choice, which is Step 9 (not yet formalized). Deferred to Step 16 (add RAG path) as originally planned.
- **Independent audit (subagent) found and we fixed one real bug:** `tickets_safe` only excluded `customer_name`/`customer_email`, but `data-notes.md` says all four PII-shaped columns are excluded "regardless" — `customer_age`/`customer_gender` were being exposed to the `sql_gen_readonly` role. My own `verify_db.py` didn't catch it because it only checked name/email. Fixed in `db/schema.sql` (view now drops all four) and `scripts/verify_db.py` (now asserts all four are absent, not just two) — reloaded and reverified, all checks pass.

## Clean data model (Step 7 — done)
Full DDL with rationale comments: `db/schema.sql`. Summary:
- **`tickets`** — base table, full fidelity to source (snake_case columns, 4 Postgres ENUMs for the categorical fields so an invalid value in generated SQL errors loudly instead of silently matching 0 rows). No `created_at`/ticket-opened column exists or is synthesized — `date_of_purchase` keeps its real meaning. `first_response_time`/`time_to_resolution` kept only for presence/absence checks, explicitly documented as not a valid duration pair (see data-notes.md follow-up finding: 49% negative deltas).
- **`tickets_safe`** (view) — same as `tickets` minus `customer_name`/`customer_email`. This is what the text-to-SQL DB role actually gets `SELECT` on (role is also read-only, granted in Step 13) — makes the Step 3/4 privacy and no-mutation guardrails enforced by Postgres itself, not just prompted for.
- **`ticket_embeddings`** — `retrieval_text` built from `ticket_type + ticket_subject + product_purchased + ticket_description` (per data-notes.md's signal/noise finding); `resolution` deliberately excluded (100% filler). pgvector HNSW index for similarity search.

## Done/good definition (Step 3 — done)
**Must-haves:**
- All 10 count/filter questions answered with exact numbers matching direct SQL.
- Correct routing (SQL vs RAG) on all 17 eval questions.
- Every answer shows its sources (SQL query run, or retrieved ticket excerpts).
- Unanswerable questions return "I don't know," never a fabricated answer.
- Read-only DB access — generated SQL can never mutate data.

**Nice-to-haves:** charts for count/filter answers; auth (downgraded — portfolio, not real ops); conversation memory/follow-ups; graceful handling of compound questions like #17.

**Success metric:** ≥80% of the 17 eval questions correct (exact match for count/filter, human-graded "reasonable + sourced" for thematic), measured **after** the Step 6/7 data cleaning (so question #16's timestamp gap doesn't count as an automatic fail). Response time <5s/question. Zero destructive-SQL incidents (hard requirement).

## Constraints and assumptions (Step 4 — done)
- **Data volume:** 8,469 rows / ~3.9MB (corrected in Step 5). Comfortably fits full-text embedding with no sampling needed; Postgres is the right choice, not overkill in practice, though this scale alone wouldn't strictly require it.
- **Where it runs:** local Docker Compose (Postgres+pgvector, FastAPI, Streamlit) during build; free/cheap public host for the final demo (Render/Fly.io for API, Streamlit Community Cloud for UI).
- **Budget:** personal/free-tier only, metered LLM API key with a hard low spend cap. Use a cheap/small model for routing + SQL-gen; reserve a stronger model for RAG summarization where quality is most visible.
- **Privacy:** dataset is the public synthetic Kaggle "Customer Support Ticket Dataset" — Name/Email/Age/Gender are Faker-generated, not real people, and the dataset is already public, so sending ticket text to an external LLM API is acceptable here. Even so, `Customer Name` and `Customer Email` are dropped from anything sent to the LLM or embedded, on principle (good habit to demonstrate, adds no analytical value).
- **Audience assumption:** no real ops team exists to design for. Default behavior (errors, refusal wording, scope) targets a technical reviewer/interviewer, so favor transparency (show SQL, show retrieved chunks) over consumer-UX polish.

## Known data issues
Full detail and cleaning decisions live in `data-notes.md` (Step 6). Summary:
- No ticket-opened/created timestamp exists. Only `Date of Purchase` (product purchase, not ticket filing) and `First Response Time`/`Time to Resolution`, confirmed in Step 5 to span only 3 distinct calendar dates (~2023-05-31–06-02) — fake generation timestamps, not real activity data. "Tickets opened last week"-style questions aren't answerable as literally worded.
- `Ticket Description` contains the literal unresolved `{product_purchased}` placeholder in **100% of rows** (confirmed in Step 5, not just a spot-check), plus random unrelated Faker-generated sentences appended after the templated opener. `Resolution` text is 100% unrelated Faker gibberish with zero usable signal. Both matter for RAG design: lean on structured fields (`Ticket Type`, `Ticket Subject`, `Product Purchased`) as primary retrieval signal, treat free text as low-signal supplementary context.

## Example questions (Step 2 — done, 17 total)
**Count/filter (SQL):**
1. How many tickets are currently open vs closed vs pending customer response?
2. How many critical-priority tickets are still open?
3. Which ticket type (technical issue, billing, cancellation, refund, product inquiry) has the most tickets?
4. How many tickets came in through each channel (social media, chat, email, phone)?
5. What's the average customer satisfaction rating for closed tickets?
6. How many refund requests are still pending a customer response?
7. Which products have the most technical-issue tickets?
8. How many tickets are tied to purchases made in 2021 vs 2020?
9. What's the average satisfaction rating broken down by channel?
10. How many high-priority tickets have no resolution recorded yet?

**Fuzzy/thematic (RAG):**
11. What are the most common technical issues customers report?
12. What do people complain about most for [a specific product]?
13. Summarize the typical reasons customers request refunds.
14. What kinds of billing inquiries come in most often?
15. Are there common themes in low-satisfaction (1-2 star) tickets?

**Mixed / router stress-tests:**
16. Which high-priority tickets are still open after 3 days? (needs the timestamp gap resolved)
17. How many tickets are complaints about GoPro Hero, and what are they mostly about? (compound: count + theme, tests router on mixed-intent questions)

## Project framing
**This is a portfolio piece**, not a real ops deployment. Implications for later steps:
- Auth is nice-to-have, not must-have (Step 3).
- Deployment target should be something demoable/public (a hosted demo, e.g. Streamlit Community Cloud / Render / Fly.io free tier), not enterprise infra (Step 18).
- README/handoff (Step 19) and retro (Step 20) should be written with an interview audience in mind — clear architecture story, honest about tradeoffs and limitations.
- "Ops team" in the problem statement below is the target *persona* the tool is designed for, even though there's no real ops team using it.

## Problem statement (Step 1 — done)
Ops and support leads currently have to manually scan through thousands of tickets to spot volume trends, priority backlogs, and recurring complaint themes. This project lets them ask questions about ticket data in plain English — counts/filters answered exactly from the database, thematic questions answered from ticket text with cited sources — and get a trustworthy answer in seconds instead of hours of manual digging.

## Working agreement
Go through the 20-step plan below **one step at a time**. After finishing a step, show the concrete output and stop — wait for explicit go-ahead before starting the next step. Do not batch multiple steps.

## Chosen architecture (already decided — don't re-litigate)
Source: Anthropic's "Building Effective AI Agents" (architecture patterns doc).

- **Top-level pattern: Routing.** A router classifies each incoming question and dispatches it to one of two specialized handlers. This was chosen over an autonomous agent because the task structure is known/repeatable (a bounded set of question shapes) and reliability matters more than open-ended adaptability.
- **Branch A — text-to-SQL**: exact/count/filter questions ("how many tickets were opened last week").
- **Branch B — RAG**: fuzzy/thematic questions ("what are people complaining about with X").
- **Guardrail, not a full Evaluator-Optimizer loop**: a thin check before returning an answer — SQL must be read-only/SELECT-only, RAG answers must cite retrieved chunks, unanswerable questions return "I don't know" rather than a guess. A full generate/critique loop was judged overkill (extra latency/cost) for this scope.
- Known biggest risk (per Step 10): routing misclassification and text-to-SQL accuracy. These get tested first, against the example-question eval set, before anything else is built on top.

## Data
- Raw file: `data/raw/customer_support_tickets.csv` (**8,469 rows** — corrected in Step 5; an earlier `wc -l` count of 29,807 was wrong, it miscounted embedded newlines inside quoted multi-line `Ticket Description` fields — 17 columns)
- Full exploration: `notebooks/01_explore.ipynb` (executed). Formal findings: `data-notes.md`.
- Columns: Ticket ID, Customer Name, Customer Email, Customer Age, Customer Gender, Product Purchased, Date of Purchase, Ticket Type, Ticket Subject, Ticket Description, Ticket Status, Resolution, Ticket Priority, Ticket Channel, First Response Time, Time to Resolution, Customer Satisfaction Rating
- This is the public Kaggle "Customer Support Ticket Dataset" — see "Known data issues" below and `data-notes.md` for the full Step 5/6 findings.
- Contains real-shaped PII columns (Customer Name, Email, Age, Gender), all Faker-generated/fake per Step 4 — dropped from anything sent to the LLM or embedded, on principle.

## The 20-step plan (from user's original message)
**Phase 1 — Understand the problem**
1. Problem statement (1-2 sentences)
2. List of 10-15 real example questions users would ask (becomes the eval set later)
3. Define "done" and "good" (must-haves, nice-to-haves, success metric)
4. Constraints and assumptions (data volume, deployment, budget, privacy)

**Phase 2 — Look at the data**
5. Explore the data in a notebook (columns, types, missing values, distributions, raw rows)
6. Write a short data-notes file (problems found, e.g. templated text, missing categories)
7. Design the clean data model (target tables, standardized values)

**Phase 3 — System design**
8. Draw the high-level flow (router → text-to-SQL / RAG)
9. For each component, pick tech + write down why (and rejected alternatives)
10. Identify the riskiest parts, test those first
11. Think through failure and safety (bad SQL, unanswerable questions, API down)

**Phase 4 — Build in thin slices**
12. Project skeleton (repo, folders, .env, README) — **already started**
13. Data pipeline: clean → load into Postgres, verify with manual SQL
14. One ugly-but-working end-to-end path (text-to-SQL only, script, no UI)
15. Turn example questions into an eval script now; run against the thin version
16. Add RAG path, then the router; re-run evals after each addition
17. Wrap it: API, then UI
18. Deploy; test the deployed version with the same eval questions

**Phase 5 — Hand off**
19. Handoff README: problem, architecture diagram, how to run, eval results, known limitations, next steps
20. Short personal retrospective

## Rough time budget
~20% understanding/data exploration, 15% design, 50% build/iterate, 15% evals+deploy+docs.
