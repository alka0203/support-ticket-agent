-- Read-only role for the text-to-SQL branch's DB connection (Step 7 design
-- decision, applied here). Granted SELECT on tickets_safe only — never the
-- base tickets table (which has customer_name/email) and never
-- ticket_embeddings. No INSERT/UPDATE/DELETE grant exists at all, so even a
-- successfully-injected mutating statement from a misbehaving LLM call fails
-- at the database level, not just at the application/prompt level.
--
-- Password is passed in via psql -v (see scripts/load_to_postgres.py), never
-- hardcoded here.
CREATE ROLE sql_gen_readonly LOGIN PASSWORD :'sql_gen_password';
GRANT CONNECT ON DATABASE support_tickets TO sql_gen_readonly;
GRANT USAGE ON SCHEMA public TO sql_gen_readonly;
GRANT SELECT ON tickets_safe TO sql_gen_readonly;
