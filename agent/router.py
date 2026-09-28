"""Router: classify an incoming question as 'sql', 'rag', or 'unknown'."""
import anthropic

from agent.prompts import ROUTER_SYSTEM_PROMPT

_client = anthropic.Anthropic()
_MODEL = "claude-haiku-4-5-20251001"


def route(question: str) -> str:
    """Return 'sql', 'rag', or 'unknown'."""
    msg = _client.messages.create(
        model=_MODEL,
        max_tokens=10,
        system=ROUTER_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": question}],
    )
    label = msg.content[0].text.strip().lower()
    if label not in ("sql", "rag", "unknown"):
        return "unknown"
    return label
