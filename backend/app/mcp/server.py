"""
MCP server exposing the building's live state and control surface as tools.

This is the "Cognitive Engine & Protocol" piece of the spec: the LLM never
touches EnergyPlus or Supabase directly, it calls these standardized MCP
tools. That indirection is what lets the same agent later run unmodified
against a different building model, simulator, or BMS -- swap the tool
implementations behind the protocol, not the agent's reasoning.

Run standalone (e.g. so a remote LLM host like Claude Desktop can attach):
    python -m app.mcp.server

Embedded mode (used by `app.main` for the closed-loop demo) skips this
process entirely and calls the functions in `tools.py` directly -- see that
module's docstring for why.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.config import settings
from app.mcp import tools

mcp = FastMCP("ecoloop-building-agent")

mcp.tool()(tools.list_zones)
mcp.tool()(tools.get_current_telemetry)
mcp.tool()(tools.get_grid_carbon)
mcp.tool()(tools.get_recent_errors)
mcp.tool()(tools.set_zone_setpoint)


def main() -> None:
    if settings.mcp_transport == "sse":
        mcp.run(transport="sse", host=settings.mcp_sse_host, port=settings.mcp_sse_port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
