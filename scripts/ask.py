#!/usr/bin/env python3
"""CLI for the support ticket insights agent.

Step 14: text-to-SQL path only. RAG path added in Step 16.

Usage (from repo root):
    python scripts/ask.py "How many open tickets are there?"
    python scripts/ask.py "Which products have the most technical-issue tickets?"
    python scripts/ask.py "What are people complaining about with GoPro Hero?"
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from agent.router import route
from agent.sql_gen import ask_sql
from agent.rag import ask_rag


def _print_rows(rows: list[dict]) -> None:
    if not rows:
        return
    # Align columns for readability
    keys = list(rows[0].keys())
    col_widths = {k: max(len(str(k)), max(len(str(r[k])) for r in rows)) for k in keys}
    header = "  ".join(str(k).ljust(col_widths[k]) for k in keys)
    sep = "  ".join("-" * col_widths[k] for k in keys)
    print(header)
    print(sep)
    for row in rows:
        print("  ".join(str(row[k]).ljust(col_widths[k]) for k in keys))


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/ask.py \"your question here\"")
        sys.exit(1)

    question = " ".join(sys.argv[1:])
    print(f"Question : {question}")
    print()

    label = route(question)
    print(f"Router   : {label}")
    print()

    if label == "sql":
        result = ask_sql(question)

        print(f"Answer   : {result['answer']}")

        if result["error"]:
            print(f"Error    : {result['error']}")

        if result["sql"]:
            print()
            print("SQL:")
            print(result["sql"])

        if result["rows"] and len(result["rows"]) > 1:
            print()
            print(f"Results ({len(result['rows'])} row(s)):")
            _print_rows(result["rows"])

    elif label == "rag":
        result = ask_rag(question)
        print(f"Answer   : {result['answer']}")
        if result["error"]:
            print(f"Error    : {result['error']}")
        if result["sources"]:
            print()
            print(f"Sources ({len(result['sources'])} tickets):")
            for s in result["sources"]:
                print(f"  #{s['ticket_id']:>5}  sim={s['similarity']:.3f}  "
                      f"{s['product']:<30}  {s['type']:<22}  {s['subject']}")

    else:
        print("Answer   : I don't know — this question is outside the scope of the ticket data,")
        print("           or the data doesn't contain what's needed to answer it.")


if __name__ == "__main__":
    main()
