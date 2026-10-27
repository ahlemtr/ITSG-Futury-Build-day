"""RAG chat assistant (HANDOUT agenda 4, llm/agents/chat.py): a question in, a cited answer out."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from api.routes.common import ai, kb
from llm.agents import chat

router = APIRouter()


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class ChatBody(BaseModel):
    question: str
    history: list[Turn] = []
    language: Literal["de", "en"] = "de"


@router.post("/chat")
def ask(request: Request, body: ChatBody):
    """`answer` is null when the model is unavailable or gave no valid cited answer; `context` (the retrieved
    passages with rules, changes and test cases) is always there, so the UI can show the sources at least."""
    context = chat.retrieve(kb(request), body.question)
    out = ai(request).chat(body.question, [t.model_dump() for t in body.history], body.language, context) \
        if ai(request) else None
    cited = set(out.citations) if out else set()
    return {"question": body.question,
            "answer": out.answer if out else None,
            "citations": out.citations if out else [],
            "rules": out.rules if out else [],
            "test_cases": out.test_cases if out else [],
            "context": [c | {"cited": c["key"] in cited} for c in context]}
