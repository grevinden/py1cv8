"""Check blob field names for graph example objects."""
import re
import json
from py1cv8.blob_fetch import fetch_blob

url = "postgresql+psycopg2://postgres@localhost:5433/MessageCenter"

# Check InfoRg148 (ПодпискиНаУведомления) fields
blobs = fetch_blob(url, uuid="77973d82-03d9-4e0e-84cc-3e6f55ec2a86", limit=1)
if blobs and blobs[0].get("content"):
    txt = blobs[0]["content"]
    print("=== InfoRg148 blob (first 1500 chars) ===")
    print(repr(txt[:1500]))
    print("\n\n=== Field name patterns ===")
    matches = list(re.finditer(r'\{1,0,([^}]+)\},"([^"]+)"', txt))
    for i, m in enumerate(matches):
        print(f"  [{i}] UUID={m.group(1)}, name=\"{m.group(2)}\"")

print("\n" + "="*60)

# Check Document209 (Уведомления) which has _VT254 (tabular section)
blobs2 = fetch_blob(url, uuid="e70db5ca-460d-4fb5-bc6e-6460d67278cf", limit=1)
if blobs2 and blobs2[0].get("content"):
    txt2 = blobs2[0]["content"]
    print("\n=== Document209 blob (first 1500 chars) ===")
    print(repr(txt2[:1500]))
    print("\n\n=== Field name patterns ===")
    matches2 = list(re.finditer(r'\{1,0,([^}]+)\},"([^"]+)"', txt2))
    for i, m in enumerate(matches2):
        print(f"  [{i}] UUID={m.group(1)}, name=\"{m.group(2)}\"")

print("\n" + "="*60)

# Check _Reference53 (Алгоритмы) 
blobs3 = fetch_blob(url, uuid="cd070a4a-6274-4576-8cc1-f17696a76834", limit=1)
if blobs3 and blobs3[0].get("content"):
    txt3 = blobs3[0]["content"]
    print("\n=== Reference53 (Алгоритмы) blob ===")
    print(repr(txt3[:1500]))
    print("\n\n=== Field name patterns ===")
    matches3 = list(re.finditer(r'\{1,0,([^}]+)\},"([^"]+)"', txt3))
    for i, m in enumerate(matches3):
        print(f"  [{i}] UUID={m.group(1)}, name=\"{m.group(2)}\"")
