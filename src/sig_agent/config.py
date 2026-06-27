"""Central configuration, loaded from environment (.env).

Keeping every tunable in one place makes the reasoning bounds (W, D, B,
thresholds) auditable and reproducible — a requirement under SOC2.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # dotenv is optional; env vars may be set by the host instead
    pass


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    # LLM
    llm_provider: str = os.getenv("LLM_PROVIDER", "openai")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")

    # Embeddings
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")

    # Vector DB
    chroma_persist_dir: str = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma")
    sop_collection: str = os.getenv("SOP_COLLECTION", "sop_corpus")
    sig_collection: str = os.getenv("SIG_COLLECTION", "sig_history")

    # Chunking
    chunk_max_words: int = _int("CHUNK_MAX_WORDS", 1000)
    chunk_overlap_words: int = _int("CHUNK_OVERLAP_WORDS", 200)

    # Reasoning bounds (Tree of Thoughts)
    beam_width: int = _int("BEAM_WIDTH", 2)            # W
    max_depth: int = _int("MAX_DEPTH", 3)              # D
    branch_factor: int = _int("BRANCH_FACTOR", 5)      # B
    relevance_threshold: float = _float("RELEVANCE_THRESHOLD", 0.45)
    critic_min_score: int = _int("CRITIC_MIN_SCORE", 3)

    # Hybrid search blend (semantic vs keyword)
    semantic_weight: float = _float("SEMANTIC_WEIGHT", 0.6)
    keyword_weight: float = _float("KEYWORD_WEIGHT", 0.4)
    enable_reranker: bool = _bool("ENABLE_RERANKER", True)   # cross-encoder rerank

    # Max concurrent LLM calls within a single beam-search depth expansion.
    # Keep low to stay within OpenAI RPM limits. Separate from max_workers
    # (which controls parallel questionnaire items at the orchestrator level).
    beam_max_workers: int = _int("BEAM_MAX_WORKERS", 2)

    # Conflict-detection sensitivity for beam branch comparison.
    # Answers with SequenceMatcher ratio >= this value are treated as
    # complementary (same policy, different phrasing) rather than conflicting.
    answer_similarity_threshold: float = _float("ANSWER_SIMILARITY_THRESHOLD", 0.55)

    # M6 input guardrails
    enable_input_guard: bool = _bool("ENABLE_INPUT_GUARD", True)
    min_question_chars: int = _int("MIN_QUESTION_CHARS", 8)
    max_question_chars: int = _int("MAX_QUESTION_CHARS", 4000)

    # Serving / runtime
    max_workers: int = _int("MAX_WORKERS", 4)
    api_key: str = os.getenv("SIG_API_KEY", "")
    mcp_transport: str = os.getenv("MCP_TRANSPORT", "stdio")
    mcp_host: str = os.getenv("MCP_HOST", "0.0.0.0")
    mcp_port: int = _int("MCP_PORT", 8000)


settings = Settings()
