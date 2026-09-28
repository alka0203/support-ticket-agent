-- Clean data model for the Support Ticket Insights Agent (Step 7).
-- Design decisions are explained inline; see data-notes.md for the full findings
-- these decisions come from.

CREATE EXTENSION IF NOT EXISTS vector;

-- Standardized categorical values: lowercase snake_case everywhere, enforced by
-- Postgres ENUM types rather than free TEXT + a CHECK, so that a generated SQL
-- query using an invalid value fails loudly (a clear error) instead of silently
-- matching zero rows and producing a confidently wrong "0 tickets" answer.
CREATE TYPE ticket_type_enum AS ENUM (
    'technical_issue', 'billing_inquiry', 'cancellation_request',
    'refund_request', 'product_inquiry'
);
CREATE TYPE ticket_status_enum AS ENUM (
    'open', 'closed', 'pending_customer_response'
);
CREATE TYPE ticket_priority_enum AS ENUM (
    'low', 'medium', 'high', 'critical'
);
CREATE TYPE ticket_channel_enum AS ENUM (
    'email', 'phone', 'chat', 'social_media'
);

-- Base table. Full fidelity to source, including PII-shaped columns — kept here
-- because this is the source of truth loaded from the raw CSV, and access
-- control (below) is what actually enforces the Step 4 privacy decision, not
-- omission from this table.
--
-- No `created_at` / ticket-opened column: per data-notes.md, none exists in the
-- source, and none is synthesized. `date_of_purchase` is kept under its real
-- name — it means "product purchase date," never treated as ticket recency.
--
-- `first_response_time` / `time_to_resolution` are kept as raw timestamps for
-- presence/absence questions only (e.g. "high-priority tickets with no
-- resolution recorded"). Per data-notes.md's follow-up finding, the delta
-- between them is NOT a valid duration (49% negative) — application code and
-- the SQL-gen system prompt must never compute or present an average/derived
-- "time to resolve" from these two columns.
CREATE TABLE tickets (
    ticket_id                      INTEGER PRIMARY KEY,
    customer_name                  TEXT NOT NULL,
    customer_email                 TEXT NOT NULL,
    customer_age                   INTEGER NOT NULL,
    customer_gender                TEXT NOT NULL,
    product_purchased              TEXT NOT NULL,
    date_of_purchase               DATE NOT NULL,
    ticket_type                    ticket_type_enum NOT NULL,
    ticket_subject                 TEXT NOT NULL,
    ticket_description             TEXT NOT NULL,
    ticket_status                  ticket_status_enum NOT NULL,
    resolution                     TEXT,               -- NULL unless status = closed
    ticket_priority                ticket_priority_enum NOT NULL,
    ticket_channel                 ticket_channel_enum NOT NULL,
    first_response_time            TIMESTAMPTZ,         -- NULL if status = open; NOT a reliable clock, see note above
    time_to_resolution             TIMESTAMPTZ,         -- NULL unless status = closed; NOT a reliable clock, see note above
    customer_satisfaction_rating   NUMERIC(2,1)         -- NULL unless status = closed
);

CREATE INDEX idx_tickets_status   ON tickets (ticket_status);
CREATE INDEX idx_tickets_type     ON tickets (ticket_type);
CREATE INDEX idx_tickets_priority ON tickets (ticket_priority);
CREATE INDEX idx_tickets_channel  ON tickets (ticket_channel);
CREATE INDEX idx_tickets_product  ON tickets (product_purchased);

-- PII-free view. This — not the base table — is what the text-to-SQL branch's
-- database role is granted SELECT on. Combined with that role being read-only
-- (no INSERT/UPDATE/DELETE grants, enforced at the Postgres role level in
-- Step 13), this is the concrete implementation of two Step 3/4 guardrails at
-- once: "generated SQL can never mutate data" and "customer_name/email never
-- reach the LLM," enforced by the database itself rather than by trusting the
-- LLM's system prompt to behave.
CREATE VIEW tickets_safe AS
SELECT
    ticket_id,
    customer_age,
    customer_gender,
    product_purchased,
    date_of_purchase,
    ticket_type,
    ticket_subject,
    ticket_description,
    ticket_status,
    resolution,
    ticket_priority,
    ticket_channel,
    first_response_time,
    time_to_resolution,
    customer_satisfaction_rating
FROM tickets;

-- RAG retrieval corpus. `retrieval_text` is built at load time from the fields
-- data-notes.md identified as carrying real signal (ticket_type, ticket_subject,
-- product_purchased) plus ticket_description as supplementary low-signal
-- context. `resolution` is deliberately excluded — confirmed 100% unrelated
-- filler text, pure noise for retrieval.
CREATE TABLE ticket_embeddings (
    ticket_id       INTEGER PRIMARY KEY REFERENCES tickets(ticket_id),
    retrieval_text  TEXT NOT NULL,
    embedding       VECTOR(384)  -- dim matches whichever sentence-transformers model Step 9 picks
);

CREATE INDEX idx_ticket_embeddings_vector
    ON ticket_embeddings USING hnsw (embedding vector_cosine_ops);
