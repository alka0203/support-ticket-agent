"""FastAPI application for the Support Ticket Insights Agent.

Single endpoint: POST /ask
GET  /health — liveness check

Run (from repo root, venv active):
    uvicorn api.main:app --reload --port 8000
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent.router import route
from agent.sql_gen import ask_sql
from agent.rag import ask_rag
from agent.db import get_admin_conn


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: verify DB is reachable before accepting requests.
    try:
        conn = get_admin_conn()
        conn.close()
    except Exception as exc:
        raise RuntimeError(
            f"Cannot connect to Postgres on startup: {exc}\n"
            "Make sure Docker Compose is running: docker compose up -d"
        ) from exc
    yield


app = FastAPI(
    title="Support Ticket Insights Agent",
    description="Ask questions about customer support tickets in plain English.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    question: str
    route: str                      # "sql" | "rag" | "unknown"
    answer: str
    sql: str | None = None          # SQL branch: the query that ran
    rows: list[dict] | None = None  # SQL branch: result rows
    sources: list[dict] | None = None  # RAG branch: retrieved tickets
    error: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question must not be empty")

    label = route(question)

    if label == "sql":
        result = ask_sql(question)
        return AskResponse(
            question=question,
            route=label,
            answer=result["answer"],
            sql=result["sql"],
            rows=result["rows"] if result["rows"] else None,
            error=result["error"],
        )

    if label == "rag":
        result = ask_rag(question)
        return AskResponse(
            question=question,
            route=label,
            answer=result["answer"],
            sources=result["sources"] if result["sources"] else None,
            error=result["error"],
        )

    # unknown / out-of-scope
    return AskResponse(
        question=question,
        route="unknown",
        answer=(
            "I don't know — this question is outside the scope of the ticket data, "
            "or the data doesn't contain what's needed to answer it."
        ),
    )
