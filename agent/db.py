"""Database connections for the support ticket agent."""
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

# Load .env from the project root (two levels up from this file).
load_dotenv(Path(__file__).parent.parent / ".env")


def get_sql_gen_conn():
    """psycopg2 connection as sql_gen_readonly (SELECT on tickets_safe only)."""
    return psycopg2.connect(
        host="localhost",
        port=os.environ["POSTGRES_PORT"],
        dbname=os.environ["POSTGRES_DB"],
        user="sql_gen_readonly",
        password=os.environ["SQL_GEN_DB_PASSWORD"],
    )


def get_admin_conn():
    """psycopg2 connection as the admin user (full access).

    Used by the RAG path for hardcoded embedding-search queries — not for
    LLM-generated SQL. The security constraint (SELECT-only on tickets_safe)
    applies to the sql_gen_readonly role; RAG runs our own fixed queries.
    """
    return psycopg2.connect(
        host="localhost",
        port=os.environ["POSTGRES_PORT"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )
