"""Verify UUID mixed-endian format in 1C _IDRRef."""

import sqlalchemy as sa

url = "postgresql+psycopg2://postgres@localhost:5433/MessageCenter"
eng = sa.create_engine(url)
conn = eng.connect()

# Get raw _idrref from _Reference117
rows = conn.execute(
    sa.text("SELECT encode(_idrref, 'hex') AS raw_hex, _description FROM _reference117 LIMIT 5")
).fetchall()

print("Raw _idrref bytes -> standard UUID conversion:")
for r in rows:
    raw = r[0]
    std = (
        f"{raw[6:8]}{raw[4:6]}{raw[2:4]}{raw[0:2]}"
        f"-{raw[10:12]}{raw[8:10]}"
        f"-{raw[14:16]}{raw[12:14]}"
        f"-{raw[16:20]}"
        f"-{raw[20:]}"
    )
    print(f"  raw={raw} -> std={std}  desc={r[1]}")

# Also check _fld120_rrref (from _InfoRg119) - is it also mixed-endian?
rows2 = conn.execute(
    sa.text("SELECT encode(_fld120_rrref, 'hex') AS raw_hex FROM _inforg119 WHERE length(_fld120_rrref)=16 LIMIT 3")
).fetchall()
print()
print("_fld120_rrref raw hex (standard UUID?):")
for r in rows2:
    raw = r[0]
    std = (
        f"{raw[6:8]}{raw[4:6]}{raw[2:4]}{raw[0:2]}"
        f"-{raw[10:12]}{raw[8:10]}"
        f"-{raw[14:16]}{raw[12:14]}"
        f"-{raw[16:20]}"
        f"-{raw[20:]}"
    )
    print(f"  raw={raw} -> std={std}")

conn.close()
eng.dispose()
print("Done")
