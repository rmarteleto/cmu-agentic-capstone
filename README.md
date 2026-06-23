# SIG Agent

Use agents to answer Standardized Information Gathering (SIG) security
questionnaires for a SOC2 Type II FinTech vendor. Every answer is grounded in two
private corpora — corporate **SOPs** (compliance ground truth) and historical
**SIG** Q/A pairs (candidate answers) — independently validated, and routed to a
human when confidence is low or sources conflict.

## Layout

```
sig-agent/
├── .claude-plugin/
│   ├── plugin.json            # declares the MCP server (python -m sig_agent.mcp)
│   └── marketplace.json       # plugin marketplace entry
├── agents/                    # agent definitions (markdown, one per agent)
│   ├── sig-assistant.md       #   orchestrator — delegates via the Agent tool
│   ├── retriever.md           #   sub-agent: dual-corpus hybrid retrieval
│   ├── interpreter.md         #   sub-agent: candidate SOP→question mappings
│   ├── compliance-critic.md   #   sub-agent: independent validation / pruning
│   └── synthesizer.md         #   sub-agent: cited final answer + review flag
├── skills/                    # skills (folder per skill, each with SKILL.md)
│   ├── hybrid-retrieval/
│   ├── precedence-resolution/
│   ├── compliance-validation/
│   ├── conflict-escalation/
│   └── questionnaire-fill/
├── src/sig_agent/             # Python package (the tools + engine)
│   ├── mcp/                   #   MCP server + tool registration
│   │   ├── __main__.py        #     entry: python -m sig_agent.mcp
│   │   ├── setup.py           #     registers sig_* tools on a FastMCP server
│   │   ├── service.py         #     bridge to the orchestration engine
│   │   ├── rest_api.py        #     FastAPI adapter (Copilot Studio connector)
│   │   ├── openai_compat.py   #     OpenAI-compatible /v1 shim for Open-WebUI
│   │   ├── types.py           #     tool I/O contract
│   │   └── utils.py           #     serialization + auth helpers
│   ├── orchestration/         #   Orchestrator + interpreter/critic/synth/retriever
│   ├── reasoning/             #   Tree-of-Thoughts beam search + precedence rules
│   ├── retrieval/             #   hybrid (semantic + BM25) search + rerank
│   ├── ingestion/             #   SOP/SIG ingestion, structure-aware chunking, Chroma
│   ├── state/                 #   data models + MCP-style shared-state blackboard
│   ├── llm/                   #   OpenAI/Anthropic chat + embedding adapters
│   ├── io/                    #   SIG spreadsheet read/write
│   └── config.py
├── tests/                     # deterministic unit tests (no network/LLM)
├── deploy/ · openapi/         # Copilot Studio deployment guide + connector spec
├── main.py                    # convenience CLI (ask | fill | ingest)
├── pyproject.toml             # src layout, deps, pytest config (uv-compatible)
└── requirements.txt           # pip alternative
```

## Agents and sub-agents

| Agent | Kind | Responsibility |
|-------|------|----------------|
| `sig-assistant` | orchestrator | Coordinates the pipeline, runs the bounded beam search, owns the human-escalation gate. Delegates via the `Agent` tool. |
| `retriever` | sub-agent | Hybrid dual-corpus search; applies the relevance gate. |
| `interpreter` | sub-agent | Generates candidate interpretations (divergent step). |
| `compliance-critic` | sub-agent | Independently scores and prunes candidates. |
| `synthesizer` | sub-agent | Assembles the cited answer; sets the review flag. |

## Tools (MCP, `sig_*`)

Registered in `src/sig_agent/mcp/setup.py`, all domain-prefixed (`sig_*`):

| Tool | Purpose |
|------|---------|
| `sig_answer_question` | Full pipeline for one item → answer + status + citations. |
| `sig_answer_batch` | Parallel pipeline for many items. |
| `sig_retrieve` | Dual-corpus hybrid retrieval only (used by the retriever sub-agent). |
| `sig_ingest` | Rebuild the SOP/SIG vector index from local files (human-led update). |

## Install (plugin)

```
/plugin marketplace add your-org/sig-agent
/plugin install sig-agent@sig-agent --scope user
```

The plugin starts the MCP server via `uv run -m sig_agent.mcp`.

## Development

```bash
git clone <repo> && cd sig-agent
uv sync                      # or: pip install -e .
cp .env.example .env         # LLM key + Azure storage creds + reasoning bounds
python -m sig_agent.mcp      # run the MCP server (stdio)
```

Convenience CLI:

```bash
python main.py ingest --sops data/sops/*.docx --sigs data/sig.txt
python main.py ask "Do you encrypt customer data at rest?"
python main.py fill data/sample/sample_sig.xlsx --out filled_sig.xlsx
```

## Tests

```bash
pytest -q     # 11 deterministic tests: precedence rules + beam search + escalation
```

The precedence engine and beam-search controller (including early
conflict-escalation) are fully tested without any LLM or network calls.

## Chat UI (Open-WebUI)

For a human chat front-end, the REST service also exposes an **OpenAI-compatible**
surface (`/v1/models`, `/v1/chat/completions`) — the SIG engine *is* the model, so
no external LLM is needed in the UI. Each prompt runs the full SOP-grounded
pipeline and returns a cited answer with status, confidence, and the review flag.

```bash
cp .env.example .env     # set OPENAI_API_KEY (engine), AZURE_*, SIG_API_KEY
docker compose -f deploy/docker-compose.openwebui.yml up --build
# open http://localhost:3000 — model "sig-agent" is preselected
```

Point any OpenAI client at `http://localhost:8080/v1` with model `sig-agent`.
Interaction surfaces overall: **chat UI** (Open-WebUI), **CLI** (`main.py`),
**MCP** (Claude Code plugin), **REST** (`/answer`, `/answer-batch`), and the
**Copilot Studio** custom connector.

