"""A two-tool MCP server used by the MCP target's tests.

Run over stdio as a child process (`python tests/fixtures/mcp_fixture_server.py`),
so the tests exercise a real MCP transport rather than a stub. It exposes
`add` and `echo`, both pure, so a test can assert on exact output.

Contract: the process speaks MCP over stdin/stdout and writes nothing else
to stdout; anything printed there would corrupt the JSON-RPC stream. It runs
until its stdin closes, which is how the Inspect client shuts it down.

Uses `mcp.server.mcpserver.MCPServer`, the mcp 2.x name for what mcp 1.x
called `FastMCP`; the package's 2.x line is what the `mcp` extra resolves to.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

server = MCPServer("eval-platform-fixture")


@server.tool()
def add(a: int, b: int) -> int:
    """Add two integers and return the sum."""
    return a + b


@server.tool()
def echo(text: str) -> str:
    """Return `text` unchanged."""
    return text


if __name__ == "__main__":
    server.run()
