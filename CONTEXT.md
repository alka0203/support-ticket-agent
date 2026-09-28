# Support Ticket Insights Agent — Project Context

## Status
Steps 1-4 done. Next action: Phase 2, Step 5 (explore the data in a notebook).

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
- **Data volume:** 29,807 rows / ~3.9MB. Comfortably fits full-text embedding with no sampling needed; Postgres is the right choice, not overkill in practice, though this scale alone wouldn't strictly require it.
- **Where it runs:** local Docker Compose (Postgres+pgvector, FastAPI, Streamlit) during build; free/cheap public host for the final demo (Render/Fly.io for API, Streamlit Community Cloud for UI).
- **Budget:** personal/free-tier only, metered LLM API key with a hard low spend cap. Use a cheap/small model for routing + SQL-gen; reserve a stronger model for RAG summarization where quality is most visible.
- **Privacy:** dataset is the public synthetic Kaggle "Customer Support Ticket Dataset" — Name/Email/Age/Gender are Faker-generated, not real people, and the dataset is already public, so sending ticket text to an external LLM API is acceptable here. Even so, `Customer Name` and `Customer Email` are dropped from anything sent to the LLM or embedded, on principle (good habit to demonstrate, adds no analytical value).
- **Audience assumption:** no real ops team exists to design for. Default behavior (errors, refusal wording, scope) targets a technical reviewer/interviewer, so favor transparency (show SQL, show retrieved chunks) over consumer-UX polish.

## Known data gap (found while writing Step 2, matters for Step 4/6/7)
No ticket-opened/created timestamp exists in the raw data. Only `Date of Purchase` (product purchase, not ticket filing) and `First Response Time`/`Time to Resolution`, which are both clustered around a single generation date (2023-06-01) — i.e. fake/non-activity timestamps. "Tickets opened last week"-style questions aren't answerable as-is. Resolve during cleaning (Step 6/7): either treat `Date of Purchase` as the closest proxy for recency, or synthesize a plausible `created_at`. Decide explicitly, don't silently default.

Also confirmed while inspecting rows: `Resolution` text is templated/Faker-style gibberish (e.g. "Case maybe show recently my computer follow.") — same synthetic-text caveat as `Ticket Description`. Both matter for RAG quality expectations.

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
- Raw file: `data/raw/customer_support_tickets.csv` (29,807 rows, 17 columns)
- Columns: Ticket ID, Customer Name, Customer Email, Customer Age, Customer Gender, Product Purchased, Date of Purchase, Ticket Type, Ticket Subject, Ticket Description, Ticket Status, Resolution, Ticket Priority, Ticket Channel, First Response Time, Time to Resolution, Customer Satisfaction Rating
- **Known quirk (from a first glance at row 1, needs full confirmation in Step 5/6):** this matches the public Kaggle "Customer Support Ticket Dataset" — `Ticket Description` text is templated (contains a literal unresolved `{product_purchased}` placeholder in at least one row) and includes fabricated PII-shaped strings (e.g. a fake billing zip). Treat descriptions as synthetic/templated, not organic free text, when designing the RAG branch and when reporting eval results — this will affect how convincing "theme" answers can look and should be called out in Step 6's data notes and Step 19's known limitations.
- Contains real-shaped PII columns (Customer Name, Email, Age, Gender) — flag as a constraint to confirm in Step 4 (can this go to an external LLM API as-is, or does it need scrubbing/hashing first?).

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
