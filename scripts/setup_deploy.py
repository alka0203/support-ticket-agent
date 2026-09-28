#!/usr/bin/env python3
"""One-shot deployment setup: schema + roles + data load + embeddings.

Run this once from the Render shell (or any fresh environment) after the
Postgres database is provisioned. Safe to re-run (idempotent).

Usage:
    python scripts/setup_deploy.py

Requires env vars: DATABASE_URL (or POSTGRES_*), SQL_GEN_DB_PASSWORD.
The embedding step also requires sentence-transformers to be installed
(it's in requirements.txt).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

print("=== Step 1/3: schema, roles, CSV load ===")
from scripts.load_to_postgres import main as load_main
load_main()

print()
print("=== Step 2/3: generate and load embeddings ===")
from scripts.embed_tickets import main as embed_main
embed_main()

print()
print("=== Step 3/3: verify ===")
import psycopg2.extras
from agent.db import get_admin_conn, get_sql_gen_conn

conn = get_admin_conn()
with conn.cursor() as cur:
    cur.execute("SELECT COUNT(*) FROM tickets")
    tickets_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ticket_embeddings")
    embeddings_count = cur.fetchone()[0]
conn.close()

ro_conn = get_sql_gen_conn()
with ro_conn.cursor() as cur:
    cur.execute("SELECT COUNT(*) FROM tickets_safe")
    safe_count = cur.fetchone()[0]
ro_conn.close()

print(f"  tickets:           {tickets_count} rows")
print(f"  ticket_embeddings: {embeddings_count} rows")
print(f"  tickets_safe:      {safe_count} rows (via sql_gen_readonly)")
print()

if tickets_count == 8469 and embeddings_count == 8469 and safe_count == 8469:
    print("Setup complete. All checks passed.")
else:
    print("WARNING: row counts don't match expected 8469. Check the output above.")
    sys.exit(1)
