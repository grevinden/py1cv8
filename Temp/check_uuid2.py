"""Check _idrref format and compare with metadata UUIDs."""
import sqlalchemy as sa
import uuid as uuid_mod

url = "postgresql+psycopg2://postgres@localhost:5433/MessageCenter"
eng = sa.create_engine(url)
conn = eng.connect()

# Get _idrref from _reference53 and convert
rows = conn.execute(
    sa.text("SELECT encode(_idrref, 'hex') AS h FROM _reference53 LIMIT 3")
).fetchall()
print("_reference53._idrref:")
for r in rows:
    raw = r[0]
    std = (
        raw[6:8] + raw[4:6] + raw[2:4] + raw[0:2] + "-"
        + raw[10:12] + raw[8:10] + "-"
        + raw[14:16] + raw[12:14] + "-"
        + raw[16:20] + "-" + raw[20:]
    )
    # Also try python uuid
    py_uuid = str(uuid_mod.UUID(bytes=bytes.fromhex(raw)))
    print(f"  raw={raw}  std={std}  py_uuid={py_uuid}")

# Now check config filenames that contain .53.
rows2 = conn.execute(
    sa.text("SELECT filename FROM config WHERE CAST(filename AS text) LIKE '%.53.%' LIMIT 5")
).fetchall()
print("\nconfig filenames matching .53.:")
for r in rows2:
    print(f"  {r[0]}")

conn.close()
eng.dispose()
