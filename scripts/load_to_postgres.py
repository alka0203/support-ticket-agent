"""Load db/schema.sql, db/roles.sql, and the cleaned ticket CSV into Postgres.

Run after `docker compose up -d` and `python scripts/clean_data.py`.
Idempotent: drops and recreates the schema objects each run, so it's safe to
re-run while iterating.
"""
import os

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

PG_HOST = "localhost"
PG_PORT = os.environ["POSTGRES_PORT"]
PG_DB = os.environ["POSTGRES_DB"]
PG_USER = os.environ["POSTGRES_USER"]
PG_PASSWORD = os.environ["POSTGRES_PASSWORD"]

CLEAN_CSV = "data/clean/tickets_clean.csv"

DROP_ALL = """
DROP VIEW IF EXISTS tickets_safe CASCADE;
DROP TABLE IF EXISTS ticket_embeddings CASCADE;
DROP TABLE IF EXISTS tickets CASCADE;
DROP TYPE IF EXISTS ticket_type_enum CASCADE;
DROP TYPE IF EXISTS ticket_status_enum CASCADE;
DROP TYPE IF EXISTS ticket_priority_enum CASCADE;
DROP TYPE IF EXISTS ticket_channel_enum CASCADE;
DROP ROLE IF EXISTS sql_gen_readonly;
"""

# tickets columns in db/schema.sql order, excluding retrieval_text (that
# column belongs to ticket_embeddings, populated once Step 9/16 pick an
# embedding model — not part of this load).
TICKETS_COLUMNS = [
    "ticket_id", "customer_name", "customer_email", "customer_age", "customer_gender",
    "product_purchased", "date_of_purchase", "ticket_type", "ticket_subject",
    "ticket_description", "ticket_status", "resolution", "ticket_priority",
    "ticket_channel", "first_response_time", "time_to_resolution",
    "customer_satisfaction_rating",
]


def apply_ddl(cur) -> None:
    print("Dropping existing schema objects (idempotent re-run)...")
    cur.execute(DROP_ALL)

    print("Applying db/schema.sql...")
    with open("db/schema.sql") as f:
        cur.execute(f.read())

    print("Applying db/roles.sql...")
    with open("db/roles.sql") as f:
        role_sql = f.read().replace(":'sql_gen_password'", "%s")
    cur.execute(role_sql, (os.environ["SQL_GEN_DB_PASSWORD"],))


def load_tickets(engine) -> int:
    df = pd.read_csv(CLEAN_CSV)[TICKETS_COLUMNS]
    df.to_sql("tickets", engine, if_exists="append", index=False, method="multi", chunksize=1000)
    return len(df)


def main():
    admin_conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, dbname=PG_DB, user=PG_USER, password=PG_PASSWORD)
    admin_conn.autocommit = True
    with admin_conn.cursor() as cur:
        apply_ddl(cur)
    admin_conn.close()

    engine = create_engine(f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}")
    n = load_tickets(engine)
    print(f"Loaded {n} rows into tickets.")


if __name__ == "__main__":
    main()
