"""Deep inspect the blob to understand _Fld numbering."""
import re
from py1cv8.blob_fetch import fetch_blob

url = "postgresql+psycopg2://postgres@localhost:5433/MessageCenter"

# Get full blob for InfoRg148
blobs = fetch_blob(url, uuid="77973d82-03d9-4e0e-84cc-3e6f55ec2a86", limit=1)
if blobs and blobs[0].get("content"):
    txt = blobs[0]["content"]
    # Print second half to see field definitions
    print("=== MIDDLE (1500-4000) ===")
    print(repr(txt[1500:4000]))
    print("\n=== END (4000-5500) ===")
    print(repr(txt[4000:5500]))

# Also check _Document209 blob (more complex)
print("\n\n=== Document209 ===")
blobs2 = fetch_blob(url, uuid="e70db5ca-460d-4fb5-bc6e-6460d67278cf", limit=1)
if blobs2 and blobs2[0].get("content"):
    txt2 = blobs2[0]["content"]
    # Print beyond first 1500 chars
    print("CHARS 1500-4000:")
    print(repr(txt2[1500:4000]))
