"""Manual verification queries for the Step 13 data load (Postgres).
Not part of the app; a one-off sanity check to run after load_to_postgres.py."""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host="localhost", port=os.environ["POSTGRES_PORT"], dbname=os.environ["POSTGRES_DB"],
    user=os.environ["POSTGRES_USER"], password=os.environ["POSTGRES_PASSWORD"],
)
cur = conn.cursor()

print("--- row count ---")
cur.execute("SELECT count(*) FROM tickets")
print(cur.fetchone())

print("--- status breakdown (expect open=2819, closed=2769, pending=2881) ---")
cur.execute("SELECT ticket_status, count(*) FROM tickets GROUP BY 1 ORDER BY 1")
for r in cur.fetchall():
    print(r)

print("--- enum guardrail: invalid value should error ---")
try:
    cur.execute("SELECT * FROM tickets WHERE ticket_status = 'bogus_status'")
    print("BAD: no error raised")
except Exception as e:
    print("OK, errored as expected:", str(e).splitlines()[0])
conn.rollback()

print("--- tickets_safe hides PII ---")
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='tickets_safe' ORDER BY 1")
cols = [r[0] for r in cur.fetchall()]
print(cols)
print("customer_name present?", "customer_name" in cols, " customer_email present?", "customer_email" in cols)

print("--- sql_gen_readonly role: can it read tickets_safe? ---")
ro_conn = psycopg2.connect(
    host="localhost", port=os.environ["POSTGRES_PORT"], dbname=os.environ["POSTGRES_DB"],
    user="sql_gen_readonly", password=os.environ["SQL_GEN_DB_PASSWORD"],
)
ro_cur = ro_conn.cursor()
ro_cur.execute("SELECT count(*) FROM tickets_safe")
print("tickets_safe count via readonly role:", ro_cur.fetchone())

print("--- sql_gen_readonly role: blocked from base table? ---")
try:
    ro_cur.execute("SELECT * FROM tickets LIMIT 1")
    print("BAD: readonly role could read base table")
except Exception as e:
    print("OK, blocked:", str(e).splitlines()[0])
ro_conn.rollback()

print("--- sql_gen_readonly role: blocked from mutating? ---")
try:
    ro_cur.execute("DELETE FROM tickets_safe WHERE ticket_id = 1")
    print("BAD: delete succeeded")
except Exception as e:
    print("OK, blocked:", str(e).splitlines()[0])
ro_conn.rollback()

ro_conn.close()
conn.close()
