"""LLM + embedding adapters.

A single seam in front of the model backend so the agents never import a
provider SDK directly. Supports OpenAI and Anthropic via LangChain wrappers
(which CrewAI also consumes natively).
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential, wait_random_exponential

from ..config import settings


@lru_cache(maxsize=2)
def get_chat_model(temperature: float = 0.2):
    """Return a LangChain chat model. CrewAI accepts the same object."""
    provider = settings.llm_provider.lower()
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=settings.llm_model,
            anthropic_api_key=settings.anthropic_api_key,
            temperature=temperature,
        )
    # default: openai
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        temperature=temperature,
    )


@lru_cache(maxsize=1)
def get_embeddings():
    """Embedding model — MUST match the model used at ingestion time."""
    from langchain_openai import OpenAIEmbeddings
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.openai_api_key,
    )


@retry(stop=stop_after_attempt(4), wait=wait_random_exponential(multiplier=1, min=1, max=20))
def complete_json(system: str, user: str, temperature: float = 0.2) -> dict[str, Any]:
    """Prompt the model and parse a JSON object from the reply.

    Used by the Interpreter and Critic, which exchange structured verdicts.
    """
    model = get_chat_model(temperature=temperature)
    resp = model.invoke([("system", system), ("human", user)])
    content = resp.content if hasattr(resp, "content") else str(resp)
    return _extract_json(content)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object in model response: {text[:200]}")
    return json.loads(text[start : end + 1])
