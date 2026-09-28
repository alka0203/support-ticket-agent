"""Database connections for the support ticket agent.

Supports two connection styles:
- Local dev: individual POSTGRES_* env vars (set via .env)
- Render / managed Postgres: DATABASE_URL (a single connection string)

get_admin_conn()    — full access; used by RAG search and setup scripts
get_sql_gen_conn()  — sql_gen_readonly role; SELECT on tickets_safe only
"""
import os
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


def _base_conn_kwargs() -> dict:
    """Connection kwargs for the admin/owner user.

    Prefers DATABASE_URL (Render-style) over individual POSTGRES_* vars.
    """
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        r = urlparse(db_url)
        return {
            "host": r.hostname,
            "port": r.port or 5432,
            "dbname": r.path.lstrip("/"),
            "user": r.username,
            "password": r.password,
        }
    return {
        "host": "localhost",
        "port": os.environ["POSTGRES_PORT"],
        "dbname": os.environ["POSTGRES_DB"],
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
    }


def get_admin_conn():
    """psycopg2 connection as the admin user (full access).

    Used by the RAG path for hardcoded embedding-search queries and by all
    setup scripts. Not used for LLM-generated SQL.
    """
    return psycopg2.connect(**_base_conn_kwargs())


def get_sql_gen_conn():
    """psycopg2 connection as sql_gen_readonly (SELECT on tickets_safe only).

    Same host/port/dbname as the admin connection, but connects as the
    read-only role created by db/roles.sql.
    """
    kwargs = _base_conn_kwargs()
    kwargs["user"] = "sql_gen_readonly"
    kwargs["password"] = os.environ["SQL_GEN_DB_PASSWORD"]
    return psycopg2.connect(**kwargs)
