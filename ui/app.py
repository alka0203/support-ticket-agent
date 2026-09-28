"""Streamlit UI for the Support Ticket Insights Agent.

Run (from repo root, venv active — API must already be running on port 8000):
    streamlit run ui/app.py
"""
import os

import httpx
import pandas as pd
import streamlit as st

API_URL = os.environ.get("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Support Ticket Insights",
    page_icon="🎫",
    layout="centered",
)

st.title("Support Ticket Insights")
st.caption(
    "Ask questions about 8,469 customer support tickets. "
    "Count/filter questions are answered with exact SQL. "
    "Thematic questions are answered from ticket text with cited sources."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _render_response(data: dict) -> None:
    route_label = data.get("route", "unknown")
    badge = {"sql": "SQL", "rag": "RAG", "unknown": "Out of scope"}.get(route_label, route_label)
    st.markdown(f"`{badge}`")
    st.write(data["answer"])

    if data.get("error"):
        st.error(f"Error: {data['error']}")

    if route_label == "sql" and data.get("sql"):
        with st.expander("SQL query"):
            st.code(data["sql"], language="sql")
        rows = data.get("rows") or []
        if len(rows) > 1:
            with st.expander(f"Results ({len(rows)} rows)"):
                st.dataframe(pd.DataFrame(rows), use_container_width=True)

    if route_label == "rag":
        sources = data.get("sources") or []
        if sources:
            with st.expander(f"Sources ({len(sources)} tickets)"):
                df = pd.DataFrame(sources)[["ticket_id", "similarity", "product", "type", "subject"]]
                df = df.rename(columns={
                    "ticket_id": "ID", "similarity": "Sim",
                    "product": "Product", "type": "Type", "subject": "Subject",
                })
                st.dataframe(df, use_container_width=True, hide_index=True)


def _call_api(question: str) -> dict:
    try:
        resp = httpx.post(f"{API_URL}/ask", json={"question": question}, timeout=60.0)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        return {
            "question": question,
            "route": "error",
            "answer": f"Cannot reach the API at {API_URL}. Is `uvicorn api.main:app` running?",
            "error": "connection refused",
        }
    except Exception as exc:
        return {
            "question": question,
            "route": "error",
            "answer": f"Unexpected error: {exc}",
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []


# ---------------------------------------------------------------------------
# Render chat history
# ---------------------------------------------------------------------------

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.write(msg["content"])
        else:
            _render_response(msg["data"])


# ---------------------------------------------------------------------------
# Chat input — handle new question
# ---------------------------------------------------------------------------

if question := st.chat_input("Ask a question about the tickets…"):
    st.session_state.messages.append({"role": "user", "content": question})

    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            data = _call_api(question)
        _render_response(data)

    st.session_state.messages.append({"role": "assistant", "data": data})
