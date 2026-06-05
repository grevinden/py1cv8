import inspect
from mcp.server.streamable_http import StreamableHTTPServerTransport
src = inspect.getsource(StreamableHTTPServerTransport.connect)
print(src[:2000])
