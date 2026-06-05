"""Debug why fields is empty for InfoRg148."""
import json
from py1cv8.graph import _get_table_schema, _build_column_list
from py1cv8.context import build_llm_context

url = "postgresql+psycopg2://postgres@localhost:5433/MessageCenter"
ctx = build_llm_context(url)

# Get schema for _inforg148
schema = _get_table_schema(url, "_inforg148")
print("Schema columns count:", len(schema))
for c in schema:
    print(f"  col: {c['column_name']}  type: {c['data_type']}")

# Build column list
cols = _build_column_list(url, "_inforg148", "77973d82-03d9-4e0e-84cc-3e6f55ec2a86", ctx)
print("\nRef columns count:", len(cols))
for c in cols:
    print(f"  {json.dumps(c, ensure_ascii=False, default=str)}")

# Also test the full build_graph
from py1cv8.graph import build_graph
g = build_graph(url, "77973d82-03d9-4e0e-84cc-3e6f55ec2a86")
print("\n\n=== Full graph output ===")
print(json.dumps(g, ensure_ascii=False, indent=2, default=str))
