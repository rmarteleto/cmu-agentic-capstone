"""OpenAI-compatible chat shim — lets Open-WebUI (or any OpenAI client) drive
the SIG agent as if it were a chat model.

Open-WebUI talks to ``/v1/models`` and ``/v1/chat/completions``. There is no
external LLM here: the SIG multi-agent engine *is* the model. The last user
message is treated as one SIG question, run through the full pipeline, and the
grounded answer (with status, confidence, citations, and the review flag) is
returned as the assistant turn. This is the human-facing UI layer that the CLI,
MCP, and Copilot Studio surfaces did not provide.

Auth: ``Authorization: Bearer <SIG_API_KEY>`` (open if no key is configured),
matching how Open-WebUI sends its OpenAI key.
"""
from __future__ import annotations

import json
import time
import uuid

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..config import settings
from ..state.models import FinalAnswer
from . import service

router = APIRouter()

MODEL_ID = "sig-agent"


class ChatMessage(BaseModel):
    role: str
    content: str = ""


class ChatCompletionRequest(BaseModel):
    model: str = MODEL_ID
    messages: list[ChatMessage] = Field(default_factory=list)
    stream: bool = False


def _auth(authorization: str | None) -> None:
    expected = settings.api_key
    if not expected:
        return
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if token != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


def _last_user_question(messages: list[ChatMessage]) -> str:
    for m in reversed(messages):
        if m.role == "user" and m.content.strip():
            return m.content.strip()
    return ""


def _render_answer(ans: FinalAnswer) -> str:
    """Human-readable assistant turn for the chat UI."""
    if not ans.answer:
        body = f"**No match — abstained.**\n\n{ans.notes or 'Insufficient grounding.'}"
    else:
        body = ans.answer
    lines = [body, ""]
    lines.append(f"**Status:** `{ans.status.value}`  ·  "
                 f"**Confidence:** {ans.confidence:.2f}  ·  "
                 f"**Needs human review:** {'YES' if ans.needs_human_review else 'no'}")
    if ans.citations:
        lines.append("\n**Citations:**")
        for c in ans.citations:
            eff = c.effective_date.isoformat() if c.effective_date else "n/a"
            cite = f"- {c.document_id} {c.section} (v{c.version or 'n/a'}, {eff})".rstrip()
            if c.sharepoint_url:
                cite += f" — {c.sharepoint_url}"
            lines.append(cite)
    return "\n".join(lines).strip()


@router.get("/v1/models")
def list_models(authorization: str | None = Header(default=None)) -> dict:
    _auth(authorization)
    return {
        "object": "list",
        "data": [{"id": MODEL_ID, "object": "model", "created": int(time.time()),
                  "owned_by": "sig-agent"}],
    }


@router.post("/v1/chat/completions")
def chat_completions(req: ChatCompletionRequest,
                     authorization: str | None = Header(default=None)):
    _auth(authorization)
    question = _last_user_question(req.messages)
    if not question:
        raise HTTPException(status_code=400, detail="No user message provided.")

    ans = service.get_orchestrator().answer_question(question)
    text = _render_answer(ans)
    cid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())

    if req.stream:
        return StreamingResponse(
            _sse_chunks(cid, created, text),
            media_type="text/event-stream",
        )

    return {
        "id": cid,
        "object": "chat.completion",
        "created": created,
        "model": MODEL_ID,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": text},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _sse_chunks(cid: str, created: int, text: str):
    """Minimal SSE: one role delta, one content delta, one stop."""
    def frame(delta: dict, finish=None) -> str:
        payload = {
            "id": cid, "object": "chat.completion.chunk", "created": created,
            "model": MODEL_ID,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        return f"data: {json.dumps(payload)}\n\n"

    yield frame({"role": "assistant"})
    yield frame({"content": text})
    yield frame({}, finish="stop")
    yield "data: [DONE]\n\n"
