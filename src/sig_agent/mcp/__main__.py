"""Entry point for the SIG Agent MCP server.

Run directly:                python -m sig_agent.mcp
Declared in plugin.json as:  uv run -m sig_agent.mcp
"""
from __future__ import annotations

from ..config import settings
from .setup import setup_server


def main() -> None:
    server = setup_server()
    transport = settings.mcp_transport
    if transport == "streamable-http":
        server.settings.host = settings.mcp_host
        server.settings.port = settings.mcp_port
        server.run(transport="streamable-http")
    else:
        # stdio is the default transport for Claude Code / Gemini CLI plugins.
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
