"""Check MCP streamable HTTP API."""
from mcp.server.streamable_http import StreamableHTTPServerTransport
t = StreamableHTTPServerTransport("/mcp")
print(dir(t))
