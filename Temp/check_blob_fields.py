"""Check blob content for field names pattern."""
import re
from py1cv8.blob_fetch import fetch_blob

url = "postgresql+psycopg2://postgres@localhost:5433/MessageCenter"

# Blob for InfoRg148 (ПодпискиНаУведомления)
blobs = fetch_blob(url, uuid="a2db6f66-d843-46e7-85d3-be2558df257a", limit=1)

if blobs and blobs[0].get("content"):
    txt = blobs[0]["content"]
    print("=== Blob content (first 2000 chars) ===")
    print(txt[:2000])
    print("\n\n=== All {1,0,UUID},\"Name\" patterns ===")
    matches = list(re.finditer(r'\{1,0,([^}]+)\},"([^"]+)"', txt))
    for i, m in enumerate(matches):
        print(f"  [{i}] UUID={m.group(1)}, name=\"{m.group(2)}\"")
else:
    print("No blob found for a2db6f66")

    # Also try with different UUID
    print("\n--- Trying _Reference132 (КаналыОтправкиУведомлений) ---")
    blobs2 = fetch_blob(url, uuid="9deb1339-0c7c-4a26-98a6-7f9e87e5a5bc", limit=1)
    if blobs2 and blobs2[0].get("content"):
        txt2 = blobs2[0]["content"]
        print(txt2[:2000])
        print("\n=== All {1,0,UUID},\"Name\" patterns ===")
        matches2 = list(re.finditer(r'\{1,0,([^}]+)\},"([^"]+)"', txt2))
        for i, m in enumerate(matches2):
            print(f"  [{i}] UUID={m.group(1)}, name=\"{m.group(2)}\"")
