"""Text-to-SQL branch: generate a SELECT, validate it, run it, return results."""
import re

import anthropic
import psycopg2.extras

from agent.db import get_sql_gen_conn
from agent.prompts import SQL_GEN_SYSTEM_PROMPT

_client = anthropic.Anthropic()
_MODEL = "claude-haiku-4-5-20251001"

# Maximum rows to fetch — protects against accidentally large result sets.
_ROW_LIMIT = 200


def _is_select(sql: str) -> bool:
    """True if the first substantive token (after stripping comments) is SELECT."""
    no_block = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    no_line = re.sub(r"--[^\n]*", "", no_block)
    tokens = no_line.strip().split()
    return bool(tokens) and tokens[0].upper() == "SELECT"


def ask_sql(question: str) -> dict:
    """
    Generate a SELECT query for question, run it as sql_gen_readonly, return:
      {
        "answer": str,       human-readable summary of the result
        "sql":    str|None,  the query that was run (or attempted)
        "rows":   list[dict],
        "error":  str|None,
      }
    """
    msg = _client.messages.create(
        model=_MODEL,
        max_tokens=512,
        system=SQL_GEN_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": question}],
    )
    raw = msg.content[0].text.strip()

    if raw.upper().startswith("CANNOT_ANSWER:"):
        reason = raw[len("CANNOT_ANSWER:"):].strip()
        return {"answer": f"I don't know: {reason}", "sql": None, "rows": [], "error": None}

    if not _is_select(raw):
        return {
            "answer": "I generated SQL but it was not a SELECT statement and was not run.",
            "sql": raw,
            "rows": [],
            "error": "non-SELECT statement rejected",
        }

    try:
        conn = get_sql_gen_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(raw)
            rows = [dict(r) for r in cur.fetchmany(_ROW_LIMIT)]
            fetched_all = cur.fetchone() is None  # True if no more rows beyond the limit
        conn.close()
    except Exception as exc:
        return {"answer": "The query raised a database error.", "sql": raw, "rows": [], "error": str(exc)}

    truncated = not fetched_all

    if not rows:
        answer = "The query returned no rows."
    elif len(rows) == 1 and len(rows[0]) == 1:
        val = list(rows[0].values())[0]
        answer = str(val)
    else:
        suffix = f" (first {_ROW_LIMIT} shown)" if truncated else ""
        answer = f"{len(rows)} row(s) returned{suffix}."

    return {"answer": answer, "sql": raw, "rows": rows, "error": None}
