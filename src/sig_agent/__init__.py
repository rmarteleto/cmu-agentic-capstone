"""SIG Compliance Assistant — multi-agent reference implementation.

Architecture summary (see README.md / CMU Agent Spec M5):
    Orchestrator (LangChain)  -> bounded Tree-of-Thoughts beam search
    Retriever                 -> hybrid (semantic + BM25) dual-corpus search
    Interpreter (CrewAI)      -> generates candidate SOP->question interpretations
    Compliance Critic (CrewAI)-> independently scores branches
    Synthesizer               -> assembles cited, auditable answer
    SharedState (MCP-style)   -> blackboard carrying branch lineage + scores
"""
__version__ = "0.1.0"
