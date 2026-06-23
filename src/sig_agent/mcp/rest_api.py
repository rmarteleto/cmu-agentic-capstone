"""FastAPI adapter for the Power Platform custom-connector route.

Same engine as the MCP server, exposed over HTTP for Copilot Studio custom
connectors. Maps 1:1 to openapi/sig_agent_connector.yaml.

    uvicorn sig_agent.mcp.rest_api:app --host 0.0.0.0 --port 8080
"""
from __future__ import annotations

try:
    from fastapi import FastAPI, Header, HTTPException
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Install API deps:  pip install fastapi uvicorn pydantic") from exc

from . import service
from .utils import check_api_key
from .openai_compat import router as openai_router

app = FastAPI(
    title="SIG Compliance Assistant",
    version="1.0.0",
    description="Multi-agent SIG questionnaire engine (SOP-grounded, auditable).",
)

# OpenAI-compatible chat surface (/v1/models, /v1/chat/completions) — drives the
# Open-WebUI chat front-end. See deploy/docker-compose.openwebui.yml.
app.include_router(openai_router)


class AskRequest(BaseModel):
    question: str = Field(..., description="A single SIG questionnaire item.")


class BatchRequest(BaseModel):
    questions: list[str] = Field(..., description="Multiple SIG items.")


def _auth(x_api_key: str | None) -> None:
    if not check_api_key(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/answer")
def answer(req: AskRequest, x_api_key: str | None = Header(default=None)) -> dict:
    _auth(x_api_key)
    return service.answer_question(req.question)


@app.post("/answer-batch")
def answer_many(req: BatchRequest, x_api_key: str | None = Header(default=None)) -> dict:
    _auth(x_api_key)
    return {"answers": service.answer_batch(req.questions)}
