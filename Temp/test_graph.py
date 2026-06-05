"""Test graph command output format."""
import json
from py1cv8.graph import build_graph

url = "postgresql+psycopg2://postgres@localhost:5433/MessageCenter"

# Test InfoRg148 (ПодпискиНаУведомления)
g = build_graph(url, "77973d82-03d9-4e0e-84cc-3e6f55ec2a86")
print(json.dumps(g, ensure_ascii=False, indent=2, default=str))

print("\n" + "="*60)

# Test _Document209 (Уведомления)
g2 = build_graph(url, "e70db5ca-460d-4fb5-bc6e-6460d67278cf")
print(json.dumps(g2, ensure_ascii=False, indent=2, default=str))
