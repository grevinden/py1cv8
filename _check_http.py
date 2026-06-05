import inspect
from mcp.server.streamable_http import StreamableHTTPServerTransport
members = [m for m in dir(StreamableHTTPServerTransport) if not m.startswith('_')]
print('Public members:', members)
print()
src = inspect.getsource(StreamableHTTPServerTransport)
# find handle_post_message or similar
for line in src.split('\n'):
    if 'async def' in line or 'def handle' in line or 'def post' in line or 'def get' in line:
        print(line.strip())
