import inspect
from mcp.server.streamable_http import StreamableHTTPServerTransport
print(inspect.signature(StreamableHTTPServerTransport.connect))
