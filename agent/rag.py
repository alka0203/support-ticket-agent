"""RAG branch: embed question → pgvector search → Claude Sonnet summarization."""
import anthropic
import psycopg2.extras
from sentence_transformers import SentenceTransformer

from agent.db import get_admin_conn

_MODEL_NAME = "all-MiniLM-L6-v2"
_TOP_K = 15
_LLM_MODEL = "claude-sonnet-4-6"

# Lazy singletons — loaded once on first call, not at import time.
_embedder: SentenceTransformer | None = None
_client: anthropic.Anthropic | None = None


def _get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer(_MODEL_NAME)
    return _embedder


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


_RAG_SYSTEM_PROMPT = """\
You are a support ticket analyst answering questions about a customer support dataset.

You will receive a question and a set of relevant ticket excerpts retrieved by similarity
search. Each excerpt shows the ticket ID, product, type, subject, and description.

Rules:
1. Answer based ONLY on the provided excerpts — do not invent information.
2. Always cite the ticket IDs you draw from (e.g. "Tickets #123, #456 show...").
3. Ticket descriptions in this dataset are partially templated and may contain noise.
   Lean on ticket type and subject as the primary signal; treat description text as
   supplementary context.
4. If the excerpts don't contain enough signal to answer the question well, say so
   plainly rather than speculating.
5. Keep the answer concise (3-6 sentences) unless the question clearly needs more depth.\
"""


def _format_excerpts(rows: list[dict]) -> str:
    parts = []
    for r in rows:
        parts.append(
            f"[Ticket #{r['ticket_id']}] "
            f"Product: {r['product_purchased']} | "
            f"Type: {r['ticket_type']} | "
            f"Subject: {r['ticket_subject']}\n"
            f"Description: {r['ticket_description'][:300]}"
        )
    return "\n\n".join(parts)


def ask_rag(question: str) -> dict:
    """
    Embed question, retrieve top-k similar tickets, summarize with Claude Sonnet.

    Returns:
      {
        "answer":  str,
        "sources": list[dict],  ticket rows used (id, product, type, subject)
        "error":   str | None,
      }
    """
    # Embed the question
    embedder = _get_embedder()
    q_vec = embedder.encode(question, normalize_embeddings=True).tolist()

    # pgvector similarity search
    try:
        conn = get_admin_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    te.ticket_id,
                    ts.product_purchased,
                    ts.ticket_type,
                    ts.ticket_subject,
                    ts.ticket_description,
                    1 - (te.embedding <=> %s::vector) AS similarity
                FROM ticket_embeddings te
                JOIN tickets_safe ts USING (ticket_id)
                ORDER BY te.embedding <=> %s::vector
                LIMIT %s
                """,
                (q_vec, q_vec, _TOP_K),
            )
            rows = [dict(r) for r in cur.fetchall()]
        conn.close()
    except Exception as exc:
        return {"answer": "Database error during retrieval.", "sources": [], "error": str(exc)}

    if not rows:
        return {
            "answer": "No relevant tickets found in the database.",
            "sources": [],
            "error": None,
        }

    # Summarize with Claude Sonnet
    excerpts = _format_excerpts(rows)
    user_msg = f"Question: {question}\n\nRelevant ticket excerpts:\n\n{excerpts}"

    try:
        msg = _get_client().messages.create(
            model=_LLM_MODEL,
            max_tokens=512,
            system=_RAG_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        answer = msg.content[0].text.strip()
    except Exception as exc:
        return {"answer": "LLM error during summarization.", "sources": rows, "error": str(exc)}

    sources = [
        {
            "ticket_id": r["ticket_id"],
            "product": r["product_purchased"],
            "type": r["ticket_type"],
            "subject": r["ticket_subject"],
            "similarity": round(float(r["similarity"]), 3),
        }
        for r in rows
    ]

    return {"answer": answer, "sources": sources, "error": None}
