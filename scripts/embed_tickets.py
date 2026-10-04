#!/usr/bin/env python3
"""One-time batch: generate embeddings for all tickets and load into ticket_embeddings.

Idempotent: truncates ticket_embeddings and reloads on every run.
Run this once after load_to_postgres.py before using the RAG path.

Usage (from repo root, venv active):
    python scripts/embed_tickets.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import numpy as np
import psycopg2.extras
from fastembed import TextEmbedding

from agent.db import get_admin_conn

MODEL_NAME = "BAAI/bge-small-en-v1.5"
BATCH_SIZE = 256


def build_retrieval_text(row: dict) -> str:
    """Build the text we embed per ticket.

    Primary signal: ticket_type, ticket_subject, product_purchased.
    Supplementary: ticket_description (templated/noisy, but adds some context).
    Excluded: resolution (100% unrelated filler — see data-notes.md).
    """
    return (
        f"Type: {row['ticket_type']}. "
        f"Subject: {row['ticket_subject']}. "
        f"Product: {row['product_purchased']}. "
        f"{row['ticket_description']}"
    )


def main() -> None:
    print(f"Loading model {MODEL_NAME}...")
    model = TextEmbedding(MODEL_NAME)

    conn = get_admin_conn()
    conn.autocommit = False

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        print("Fetching tickets...")
        cur.execute("""
            SELECT ticket_id, ticket_type, ticket_subject, product_purchased, ticket_description
            FROM tickets_safe
            ORDER BY ticket_id
        """)
        tickets = [dict(r) for r in cur.fetchall()]

    print(f"Fetched {len(tickets)} tickets. Building retrieval texts...")
    texts = [build_retrieval_text(t) for t in tickets]

    print(f"Encoding with {MODEL_NAME} (batch_size={BATCH_SIZE})...")
    embeddings = np.array(list(model.embed(texts, batch_size=BATCH_SIZE)))
    print(f"Encoded {len(embeddings)} embeddings, dim={embeddings.shape[1]}.")

    print("Loading into ticket_embeddings (truncate + reload)...")
    with conn.cursor() as cur:
        cur.execute("TRUNCATE ticket_embeddings")
        psycopg2.extras.execute_values(
            cur,
            "INSERT INTO ticket_embeddings (ticket_id, retrieval_text, embedding) VALUES %s",
            [
                (t["ticket_id"], texts[i], embeddings[i].tolist())
                for i, t in enumerate(tickets)
            ],
            template="(%s, %s, %s::vector)",
            page_size=500,
        )
    conn.commit()
    conn.close()
    print(f"Done. {len(tickets)} rows in ticket_embeddings.")


if __name__ == "__main__":
    main()
