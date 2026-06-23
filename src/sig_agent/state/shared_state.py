"""MCP-style shared state — the blackboard coordinating all agents.

In the M4/M5 design the "Memory / State Manager" role is mapped to the Model
Context Protocol. This class is the in-process realisation of that contract:
every agent reads/writes branch states here, branch *lineage* is tracked, and
the Orchestrator consults it to make pruning + termination decisions from a
single source of truth. Swap the backing store for a real MCP server without
changing any agent code.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from typing import Optional

from .models import Branch, ReasoningNode


class SharedState:
    def __init__(self, question: str):
        self.question = question
        self._lock = threading.Lock()
        self._nodes: dict[str, ReasoningNode] = {}
        self._lineage: dict[str, Optional[str]] = {}   # node_id -> parent_id
        self._branches: dict[str, Branch] = {}
        self._event_log: list[str] = []                # append-only audit trail
        self.scratchpad: dict[str, object] = {}        # short-term working memory

    # ---- node / lineage tracking -------------------------------------
    def register_node(self, node: ReasoningNode) -> None:
        with self._lock:
            self._nodes[node.node_id] = node
            self._lineage[node.node_id] = node.parent_id
            self.log(f"node {node.node_id} (d{node.depth}) parent={node.parent_id}")

    def register_branch(self, branch: Branch) -> None:
        with self._lock:
            self._branches[branch.branch_id] = branch

    def ancestry(self, node_id: str) -> list[str]:
        """Full lineage of a node — supports auditability of any answer."""
        chain, cur = [], node_id
        while cur is not None:
            chain.append(cur)
            cur = self._lineage.get(cur)
        return list(reversed(chain))

    # ---- audit log ----------------------------------------------------
    def log(self, message: str) -> None:
        self._event_log.append(message)

    @property
    def event_log(self) -> list[str]:
        return list(self._event_log)

    def snapshot(self) -> dict:
        return {
            "question": self.question,
            "nodes": len(self._nodes),
            "branches": len(self._branches),
            "events": len(self._event_log),
        }
