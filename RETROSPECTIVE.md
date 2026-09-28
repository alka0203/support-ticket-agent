# Retrospective

Personal retrospective on building the Support Ticket Insights Agent (Steps 1-20).

---

## What went well

**The eval-first discipline.** Writing 17 concrete example questions in Step 2 and turning them into an automated eval script in Step 15 was the most valuable structural decision. It meant every build decision had a measurable target, and it caught a real failure mode early: the router correctly refusing Q16 ("tickets open after 3 days") as unanswerable looked like a routing *failure* until the eval script was written to accept "unknown" as the correct answer for that case. Without the eval, that would have been easy to misread as a bug.

**DB-level guardrails over prompt-level ones.** The decision to enforce the no-mutation and no-PII constraints in Postgres rather than (or in addition to) the system prompt made the safety story genuinely defensible. It also caught a real gap: an independent review of the codebase found that the `tickets_safe` view only excluded `customer_name` and `customer_email`, not `customer_age` and `customer_gender`, even though `data-notes.md` explicitly said all four should be excluded. A prompt-only constraint would have been just as leaky and much harder to audit.

**Routing architecture for a bounded task.** The two-branch router with an explicit third "out of scope" path turned out to be exactly right for this problem. 100% routing accuracy across 17 questions, including edge cases the router had never seen, with a single Haiku call and a concise system prompt. The instinct to resist over-engineering toward an agent loop was correct here.

**The thin-slice build order.** Building text-to-SQL first (Step 14), verifying it against the eval questions (Step 15), then adding RAG (Step 16) made each phase's failures easy to isolate. When the eval ran after Step 16, all the SQL results were stable — RAG was the only new variable.

---

## What was harder than expected

**The data quality.** I expected synthetic data to have some quirks. I didn't expect `ticket_description` to be 100% templated (with the `{product_purchased}` placeholder literally unresolved in every row), `resolution` to be 100% unrelated filler, and `first_response_time`/`time_to_resolution` to have a 49% negative delta rate. Each of these required a conscious design decision rather than a cleanup step. The data exploration phase (Step 5) ended up being more consequential than anticipated — it set hard constraints on what the RAG path could realistically deliver.

**Environment setup across sessions.** The Python environment had no virtualenv, the Postgres port was already allocated by another project, the API key had a typo, and `.env.example` got lost between sessions. None of these were deep problems, but collectively they added friction that wouldn't exist in a greenfield project where setup happens once. The lesson: a `scripts/setup_deploy.py` pattern (one idempotent setup command) is worth building earlier.

**The `DATABASE_URL` refactor.** The original `agent/db.py` read individual `POSTGRES_*` env vars at module level, which broke when the Anthropic client was initialized before `load_dotenv()` ran. Fixing this required understanding Python's module import order and restructuring where env vars were read. It would have been cleaner to design the connection layer with `DATABASE_URL` support from the start rather than retrofitting it in Step 18.

---

## What I'd do differently

**Write the eval script at Step 2, not Step 15.** The example questions were defined in Step 2. The eval script could have been a stub (questions listed, expected routes defined, everything else `TODO`) from that point. Running even a routing-only check earlier would have given faster feedback during the SQL-gen and RAG builds.

**Design the DB connection layer for portability from day one.** Supporting `DATABASE_URL` vs individual vars should have been in the initial `db.py`, not added as a Step 18 patch. It's a one-time 15-line decision that removes a class of deployment-time surprises.

**Be more explicit about the RAG quality ceiling earlier.** `data-notes.md` documented the templating problem accurately, and it did inform the retrieval design (lean on structured fields, not descriptions). But the framing in early steps was "retrieval text built from high-signal fields" — it would have been cleaner to say upfront: "RAG answers on this dataset will be structurally correct but semantically shallow, and that's the ceiling the data sets, not a failure of the implementation."

---

## What I'd do next on a real version of this

The engineering patterns here — routing, DB-level guardrails, eval-driven development — are production-ready. What isn't production-ready is the data. A real version of this project with actual customer-written ticket descriptions would produce meaningfully richer RAG answers with no code changes. The retrieval infrastructure is already correct.

Beyond data, the two most valuable additions would be conversation memory (follow-up questions are the most natural thing a user wants to do) and a compound-question handler for questions that genuinely span both branches.

---

## One-line summary

The right architecture for a bounded, reliability-critical task — routing over agents, DB-level over prompt-level safety, eval-driven development — proved out cleanly on a dataset where the data quality ended up being the honest ceiling on what the system could deliver.
