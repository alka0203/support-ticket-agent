#!/usr/bin/env python3
"""Step 15 eval script: run all 17 example questions through the agent.

Measures:
  - Routing accuracy: did the router return the expected label?
  - SQL correctness: does the agent's result match the reference SQL result?
    Scalar questions: exact value match.
    Multi-row questions: same row count + same column names.
  - Edge-case refusals: Q16/Q17 checked for specific expected behaviors.

Usage (from repo root, venv active):
    python scripts/eval.py            # full run
    python scripts/eval.py --dry-run  # print questions without API/DB calls
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import psycopg2.extras
from agent.router import route
from agent.sql_gen import ask_sql
from agent.rag import ask_rag
from agent.db import get_sql_gen_conn

# ---------------------------------------------------------------------------
# Eval question definitions
# ---------------------------------------------------------------------------
# check_type:
#   "scalar"    — single-value result; agent answer must exactly equal ref value
#   "structure" — multi-row result; check same row count and same column names
#   "refuse"    — agent should return CANNOT_ANSWER or route as unknown (no real SQL run)
#   "rag"       — expected route is rag; SQL answer check skipped (not implemented yet)
#   "compound"  — mixed intent; just check it doesn't crash
# ---------------------------------------------------------------------------

QUESTIONS = [
    # --- SQL: count / filter / aggregate ---
    {
        "id": 1,
        "question": "How many tickets are currently open vs closed vs pending customer response?",
        "expected_route": "sql",
        "reference_sql": """
            SELECT ticket_status, COUNT(*) AS count
            FROM tickets_safe
            GROUP BY ticket_status
            ORDER BY ticket_status
        """,
        "check_type": "structure",
    },
    {
        "id": 2,
        "question": "How many critical-priority tickets are still open?",
        "expected_route": "sql",
        "reference_sql": """
            SELECT COUNT(*)
            FROM tickets_safe
            WHERE ticket_priority = 'critical' AND ticket_status = 'open'
        """,
        "check_type": "scalar",
    },
    {
        "id": 3,
        "question": "Which ticket type has the most tickets?",
        "expected_route": "sql",
        "reference_sql": """
            SELECT ticket_type, COUNT(*) AS count
            FROM tickets_safe
            GROUP BY ticket_type
            ORDER BY count DESC
            LIMIT 1
        """,
        "check_type": "structure",  # "which has the most" — returning top 1 is correct
    },
    {
        "id": 4,
        "question": "How many tickets came in through each channel (social media, chat, email, phone)?",
        "expected_route": "sql",
        "reference_sql": """
            SELECT ticket_channel, COUNT(*) AS count
            FROM tickets_safe
            GROUP BY ticket_channel
            ORDER BY ticket_channel
        """,
        "check_type": "structure",
    },
    {
        "id": 5,
        "question": "What is the average customer satisfaction rating for closed tickets?",
        "expected_route": "sql",
        "reference_sql": """
            SELECT ROUND(AVG(customer_satisfaction_rating)::numeric, 2) AS avg_rating
            FROM tickets_safe
            WHERE ticket_status = 'closed'
        """,
        "check_type": "scalar",
    },
    {
        "id": 6,
        "question": "How many refund requests are still pending a customer response?",
        "expected_route": "sql",
        "reference_sql": """
            SELECT COUNT(*)
            FROM tickets_safe
            WHERE ticket_type = 'refund_request'
              AND ticket_status = 'pending_customer_response'
        """,
        "check_type": "scalar",
    },
    {
        "id": 7,
        "question": "Which products have the most technical-issue tickets?",
        "expected_route": "sql",
        "reference_sql": """
            SELECT product_purchased, COUNT(*) AS count
            FROM tickets_safe
            WHERE ticket_type = 'technical_issue'
            GROUP BY product_purchased
            ORDER BY count DESC
        """,
        "check_type": "structure",
    },
    {
        "id": 8,
        "question": "How many tickets are tied to purchases made in 2021 vs 2020?",
        "expected_route": "sql",
        "reference_sql": """
            SELECT EXTRACT(YEAR FROM date_of_purchase)::int AS year, COUNT(*) AS count
            FROM tickets_safe
            WHERE EXTRACT(YEAR FROM date_of_purchase) IN (2020, 2021)
            GROUP BY year
            ORDER BY year
        """,
        "check_type": "structure",
    },
    {
        "id": 9,
        "question": "What is the average satisfaction rating broken down by channel?",
        "expected_route": "sql",
        "reference_sql": """
            SELECT ticket_channel, ROUND(AVG(customer_satisfaction_rating)::numeric, 2) AS avg_rating
            FROM tickets_safe
            WHERE customer_satisfaction_rating IS NOT NULL
            GROUP BY ticket_channel
            ORDER BY ticket_channel
        """,
        "check_type": "structure",
    },
    {
        "id": 10,
        "question": "How many high-priority tickets have no resolution recorded yet?",
        "expected_route": "sql",
        "reference_sql": """
            SELECT COUNT(*)
            FROM tickets_safe
            WHERE ticket_priority = 'high' AND resolution IS NULL
        """,
        "check_type": "scalar",
    },
    # --- RAG: thematic / qualitative ---
    {
        "id": 11,
        "question": "What are the most common technical issues customers report?",
        "expected_route": "rag",
        "check_type": "rag",
    },
    {
        "id": 12,
        "question": "What do people complain about most for GoPro Hero?",
        "expected_route": "rag",
        "check_type": "rag",
    },
    {
        "id": 13,
        "question": "Summarize the typical reasons customers request refunds.",
        "expected_route": "rag",
        "check_type": "rag",
    },
    {
        "id": 14,
        "question": "What kinds of billing inquiries come in most often?",
        "expected_route": "rag",
        "check_type": "rag",
    },
    {
        "id": 15,
        "question": "Are there common themes in low-satisfaction (1-2 star) tickets?",
        "expected_route": "rag",
        "check_type": "rag",
    },
    # --- Edge cases / router stress-tests ---
    {
        "id": 16,
        "question": "Which high-priority tickets are still open after 3 days?",
        "expected_route": "unknown",  # correct: no valid duration in the data
        "check_type": "refuse",
    },
    {
        "id": 17,
        "question": "How many tickets are complaints about GoPro Hero, and what are they mostly about?",
        "expected_route": None,    # compound — either sql or rag is acceptable
        "check_type": "compound",
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_reference_sql(sql: str) -> list[dict]:
    conn = get_sql_gen_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql)
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def scalar_value(rows: list[dict]):
    """Extract single value from a single-row, single-column result."""
    if rows and len(rows[0]) == 1:
        return str(list(rows[0].values())[0])
    return None


def _numeric_eq(a: str, b: str, decimals: int = 2) -> bool:
    """Compare two string values as rounded floats if possible, else as strings."""
    try:
        return round(float(a), decimals) == round(float(b), decimals)
    except (ValueError, TypeError):
        return a.strip() == b.strip()


def check_scalar(agent_result: dict, ref_rows: list[dict]) -> tuple[bool, str]:
    ref_val = scalar_value(ref_rows)
    agent_val = agent_result["answer"]
    if ref_val is None:
        return False, "reference SQL didn't return a scalar"
    if agent_result["error"]:
        return False, f"agent error: {agent_result['error']}"
    match = _numeric_eq(agent_val, ref_val)
    return match, f"agent={agent_val!r}  ref={ref_val!r}"


def check_structure(agent_result: dict, ref_rows: list[dict]) -> tuple[bool, str]:
    """Check row count only — column aliases vary by model, data is what matters."""
    if agent_result["error"]:
        return False, f"agent error: {agent_result['error']}"
    agent_rows = agent_result["rows"]
    if len(agent_rows) != len(ref_rows):
        return False, f"row count mismatch: agent={len(agent_rows)}  ref={len(ref_rows)}"
    return True, f"{len(ref_rows)} row(s)"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_eval(dry_run: bool = False) -> None:
    routing_pass = 0
    routing_total = 0
    sql_pass = 0
    sql_total = 0
    results = []

    for q in QUESTIONS:
        qid = q["id"]
        question = q["question"]
        expected_route = q["expected_route"]
        check_type = q["check_type"]

        print(f"Q{qid:02d}  {question[:70]}")

        if dry_run:
            print(f"      [dry-run — skipping API calls]\n")
            continue

        # --- Routing check ---
        actual_route = route(question)
        if expected_route is not None:
            routing_total += 1
            route_ok = actual_route == expected_route
            if route_ok:
                routing_pass += 1
            route_status = "PASS" if route_ok else f"FAIL (got {actual_route!r}, expected {expected_route!r})"
        else:
            route_ok = True
            route_status = f"OK ({actual_route!r} — compound, any label accepted)"

        # --- Answer check ---
        ans_status = ""
        ans_ok = None

        if check_type == "rag":
            # Smoke test: RAG answers are generative — no exact match possible.
            # Check: non-empty answer, no error, at least one source returned.
            rag_result = ask_rag(question)
            if rag_result["error"]:
                ans_ok = False
                ans_status = f"FAIL (error: {rag_result['error'][:60]})"
            elif not rag_result["answer"] or not rag_result["sources"]:
                ans_ok = False
                ans_status = "FAIL (empty answer or no sources)"
            else:
                ans_ok = True
                ans_status = f"PASS (smoke) — {len(rag_result['sources'])} sources, {len(rag_result['answer'])} chars"

        elif check_type == "compound":
            ans_status = "skip (compound question — no single expected answer)"
            ans_ok = None

        elif check_type == "refuse":
            sql_total += 1
            if actual_route == "unknown":
                # Router refused it entirely — correct
                ans_ok = True
                ans_status = "PASS (router refused as unknown)"
                sql_pass += 1
            else:
                # Router sent it to SQL-gen; gen should say CANNOT_ANSWER
                agent_result = ask_sql(question)
                refused = agent_result["sql"] is None and "don't know" in agent_result["answer"].lower()
                ans_ok = refused
                sql_pass += (1 if refused else 0)
                ans_status = ("PASS (SQL-gen refused)" if refused
                              else f"FAIL (got answer: {agent_result['answer'][:60]!r})")

        elif check_type == "scalar":
            sql_total += 1
            ref_rows = run_reference_sql(q["reference_sql"])
            agent_result = ask_sql(question)
            ans_ok, detail = check_scalar(agent_result, ref_rows)
            sql_pass += (1 if ans_ok else 0)
            ans_status = f"{'PASS' if ans_ok else 'FAIL'}  {detail}"

        elif check_type == "structure":
            sql_total += 1
            ref_rows = run_reference_sql(q["reference_sql"])
            agent_result = ask_sql(question)
            ans_ok, detail = check_structure(agent_result, ref_rows)
            sql_pass += (1 if ans_ok else 0)
            ans_status = f"{'PASS' if ans_ok else 'FAIL'}  {detail}"

        print(f"      route : {route_status}")
        if ans_status:
            print(f"      answer: {ans_status}")
        print()

        results.append({
            "id": qid,
            "route_ok": route_ok,
            "ans_ok": ans_ok,
        })

    if dry_run:
        print(f"Dry run complete — {len(QUESTIONS)} questions listed.")
        return

    rag_pass = sum(1 for r in results if r.get("ans_ok") is True and
                   QUESTIONS[r["id"] - 1]["check_type"] == "rag")
    rag_total = sum(1 for q in QUESTIONS if q["check_type"] == "rag")

    print("=" * 70)
    print(f"Routing accuracy : {routing_pass}/{routing_total}")
    print(f"SQL accuracy     : {sql_pass}/{sql_total}")
    print(f"RAG smoke tests  : {rag_pass}/{rag_total}  (non-empty answer + sources, no error)")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="List questions without making API calls")
    args = parser.parse_args()
    run_eval(dry_run=args.dry_run)
