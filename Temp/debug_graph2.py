"""Debug _build_column_list logic directly."""
from py1cv8.graph import _get_table_schema, _extract_field_names
from py1cv8.blob_fetch import fetch_blob

url = "postgresql+psycopg2://postgres@localhost:5433/MessageCenter"

schema = _get_table_schema(url, "_inforg148")
print("Schema:")
for c in schema:
    name = c["column_name"]
    nl = name.lower()
    is_rref = nl.endswith("_rref") and not nl.endswith("_rtref")
    is_rtref = nl.endswith("_rtref")
    is_type = nl.endswith("_type")
    print(f"  {name:25s} rref={is_rref} rtref={is_rtref} type={is_type}")

# Check blob field names
blobs = fetch_blob(url, uuid="77973d82-03d9-4e0e-84cc-3e6f55ec2a86", limit=1)
if blobs and blobs[0].get("content"):
    txt = blobs[0]["content"]
    print(f"\nBlob content length: {len(txt)}")
    fnames = _extract_field_names(txt)
    print(f"Field names: {fnames}")
else:
    print("No blob found")
    # Try to find blob by searching
    blobs2 = fetch_blob(url, uuid="77973d82", limit=5)
    print(f"Search by short UUID: {len(blobs2)} results")
    for b in blobs2:
        print(f"  filename={b.get('filename')}, partno={b.get('partno')}")
        if b.get("content"):
            txt2 = b["content"]
            fnames2 = _extract_field_names(txt2)
            print(f"  field_names={fnames2}")
