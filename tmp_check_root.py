"""Decode root file from config table."""

from __future__ import annotations

import psycopg2
from py1cv8.config import DB_HOST, DB_PORT, DB_USER, DB_PASS

conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS, dbname="test")
cur = conn.cursor()

# Read root file
cur.execute("SELECT binarydata, datasize FROM config WHERE filename = 'root'")
blob = None
for b, sz in cur.fetchall():
    blob = bytes(b)[:sz]
    print(f"root blob ({len(blob)} bytes):")
    print(repr(blob[:200]))

# Read version file
cur.execute("SELECT binarydata, datasize FROM config WHERE filename = 'version'")
for b, sz in cur.fetchall():
    data = bytes(b)[:sz]
    print(f"\nversion blob ({len(data)} bytes):")
    print(repr(data))
    # Try decoding as text
    for enc in ["utf-8", "utf-8-sig", "cp1251"]:
        try:
            print(f"  {enc}: {data.decode(enc)}")
        except:
            pass

# DBNamesVersion for main DBNames
cur.execute(
    "SELECT binarydata, datasize FROM params WHERE filename = 'DBNamesVersion-DBNames'"
)
for b, sz in cur.fetchall():
    data = bytes(b)[:sz]
    text = data.decode("utf-8-sig")
    print(f"\nDBNamesVersion-DBNames: {text}")

conn.close()
