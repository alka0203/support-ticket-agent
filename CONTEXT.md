# Support Ticket Insights Agent — Project Context

## Status
Project just initialized. **No plan steps completed yet.** Next action: Phase 1, Step 1 (problem statement).

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
