# Data Notes

Findings from Step 5 exploration (`notebooks/01_explore.ipynb`), and the cleaning decisions
they lead to for Step 7 (clean data model). Source: `data/raw/customer_support_tickets.csv`,
the public Kaggle "Customer Support Ticket Dataset" (synthetic).

## Shape
- **8,469 rows, 17 columns.** (A first-pass `wc -l` on the raw CSV gave 29,807 — wrong; it
  counted embedded newlines inside quoted multi-line `Ticket Description` fields as row
  breaks. Confirmed 8,469 via pandas' CSV parser and via 8,469 unique, non-duplicated
  `Ticket ID` values.)
- No duplicate rows, no duplicate `Ticket ID`, no duplicate
  `(Customer Email, Ticket Subject, Ticket Description)` combinations.

## Missing values — all structural, not random
| Column | Missing | Missing when... |
|---|---|---|
| `Customer Satisfaction Rating` | 67.3% (5,700) | `Ticket Status != Closed` |
| `Time to Resolution` | 67.3% (5,700) | `Ticket Status != Closed` |
| `Resolution` | 67.3% (5,700) | `Ticket Status != Closed` |
| `First Response Time` | 33.3% (2,819) | `Ticket Status == Open` |

These three "closed-only" fields are null for exactly (and only) the 5,700 non-closed
tickets, and `First Response Time` is null for exactly the 2,819 `Open` tickets — i.e. the
missingness is fully explained by ticket status, not random or a data-entry problem.
**Decision:** don't impute these; leave null and treat "no resolution yet" as meaningful
signal for questions like #10 (high-priority tickets with no resolution recorded).

No blank-string values hiding behind non-null missingness checks. No other column has any
missing values.

## Critical finding: `Ticket Description` is templated in 100% of rows
Every single `Ticket Description` starts from a small set of fixed openers (e.g. *"I'm having
an issue with the {product_purchased}. Please assist."*) with the `{product_purchased}`
placeholder **left unresolved literally in the text** — never substituted with the actual
product name — followed by random, often unrelated Faker-generated sentences (spotted:
fragments of code, a fake chat log, a fake device-ID string). This is not a rare glitch; it's
every row.

**Implication:** `Ticket Description` carries much weaker topical signal than a real support
ticket corpus would. The reliable topical signal is in the *structured* fields:
`Ticket Type`, `Ticket Subject`, `Product Purchased`.

**Decision for Step 7/RAG design:** build retrieval primarily over
`Ticket Type + Ticket Subject + Product Purchased`, include `Ticket Description` as
supplementary context but don't expect it to drive thematic differentiation. State this
plainly in the eval writeup (Step 15) and known-limitations section (Step 19) rather than
letting a demo imply deeper semantic understanding than the data supports.

## Critical finding: `Resolution` text is 100% unrelated filler
Random sample of 8 non-null `Resolution` values, all equally meaningless:
*"Five tree those particular they product officer various."*,
*"School fight role shake story low inside next."*, etc. — grammatically-shaped but
semantically empty Faker sentences, unrelated to the ticket's actual subject or type.

**Decision:** exclude `Resolution` from the RAG retrieval corpus entirely. It would only add
noise, not signal.

## No ticket-opened/created timestamp
The only date-like fields are:
- `Date of Purchase` — when the *product* was bought (2020-01-01 to 2021-12-30), not when
  the ticket was filed.
- `First Response Time` / `Time to Resolution` — timestamps, but they span only **3 distinct
  calendar dates** (~2023-05-31 to 2023-06-02) across all 8,469 rows. This is a generation
  artifact (the whole file was synthesized in one run), not real activity data.

**Implication:** "tickets opened last week" (or any recency question on actual ticket filing)
is not answerable from this data as literally worded.

**Decision for Step 7:** do not silently substitute `Date of Purchase` as if it meant "ticket
opened" — that would produce confidently wrong answers to recency questions. Instead:
expose `Date of Purchase` under its real name in the clean schema, and have the SQL-gen
prompt / router explicitly know there is no ticket-creation date, so it either (a) reframes
using `Date of Purchase` when a question is genuinely about purchase recency, or (b) answers
"I don't have a ticket-filed date in this dataset" when asked about ticket recency
specifically. Eval question #16 will be used to verify this refusal behavior rather than a
guess.

**Follow-up finding (checked while designing the Step 7 schema):**
`First Response Time` and `Time to Resolution` are not a valid start/end pair either. Of the
2,769 rows where both are present, `Time to Resolution − First Response Time` is **negative
for 1,365 rows (49%)**, ranging down to −23h13m, with a near-zero median (10 min) and a
symmetric-looking spread (mean ≈ 0, std ≈ 9.6h) — the signature of two independently random
timestamps, not a real elapsed duration. **Decision:** never expose or compute an
"average time to resolution" style answer from these two columns; the clean schema keeps
them as raw timestamps (useful only for confirming presence/absence, e.g. eval Q10), and the
SQL-gen system prompt explicitly says duration math between them is invalid.

## Clean categorical fields
`Ticket Type` (5 values), `Ticket Status` (3), `Ticket Priority` (4), `Ticket Channel` (4),
`Customer Gender` (3) — no typos, no casing inconsistency, no stray categories, roughly
even distribution across each. No standardization work needed beyond snake_case column
naming in Step 7.

## Product Purchased
42 distinct products, roughly evenly distributed (~200–240 tickets each; top is
Canon EOS at 240). No cleanup needed.

## PII columns
`Customer Name`, `Customer Email`, `Customer Age`, `Customer Gender` are present and
real-shaped but Faker-generated (confirmed: public, already-published synthetic dataset).
Per the Step 4 privacy decision: excluded from anything sent to the LLM API or embedded,
regardless.
