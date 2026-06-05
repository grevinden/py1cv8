import json

with open(r"C:\Users\rasty\AppData\Local\Temp\ctx_out.json", encoding="utf-8") as f:
    ctx = json.load(f)

print(f"version: {ctx["version"]}")
print(f"db_database: {ctx["db_database"]}")
print(f"object_count: {ctx["object_count"]}")
print(f"type_map entries: {len(ctx["type_map"])}")
print()
print("First 3 objects:")
for obj in ctx["objects"][:3]:
    print(obj)
