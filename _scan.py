import re
with open(r'b:\py1cv8\src\py1cv8\mcp_server.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i, line in enumerate(lines, 1):
    m = re.match(r'^(\s*)def ', line)
    if m and len(m.group(1)) <= 4:
        print(f'{i}: {line.rstrip()}')
