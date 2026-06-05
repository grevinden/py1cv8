"""Test _owneridrref and rref resolution strategies."""
import json
from sqlalchemy import create_engine, text
from py1cv8.resolve_uuid import _uuid_to_1c_idrref_hex, _normalise_uuid
from py1cv8.context import build_llm_context

url = "postgresql+psycopg2://postgres@localhost:5433/MessageCenter"
ctx = build_llm_context(url)
eng = create_engine(url)

with eng.connect() as conn:
    # 1. Get owner UUID from _reference132  
    print("=== _reference132 owner sample ===")
    rows = conn.execute(text("""
        SELECT encode(_idrref, 'hex') AS id,
               encode(_owneridrref, 'hex') AS owner,
               _code
        FROM _reference132
        WHERE _owneridrref IS NOT NULL
        LIMIT 3
    """)).fetchall()
    for r in rows:
        raw_owner = r[1]
        # Convert 1C mixed-endian to standard UUID
        std_owner = (
            raw_owner[6:8] + raw_owner[4:6] + raw_owner[2:4] + raw_owner[0:2] + "-"
            + raw_owner[10:12] + raw_owner[8:10] + "-"
            + raw_owner[14:16] + raw_owner[12:14] + "-"
            + raw_owner[16:20] + "-" + raw_owner[20:]
        )
        print(f"  _code={r[2]}, _idrref_hex={r[0]}, owner_hex={raw_owner}, std_owner={std_owner}")

    # 2. Test: try to resolve the owner UUID against _reference117
    print("\n=== Try to resolve owner in _reference117 ===")
    # Get one owner UUID
    row = conn.execute(text("""
        SELECT encode(_owneridrref, 'hex') AS owner
        FROM _reference132
        WHERE _owneridrref IS NOT NULL
        LIMIT 1
    """)).fetchone()
    if row:
        owner_hex = row[0]
        # Convert to 1C-formatted hex for IDRRef comparison
        # owner_hex is already 1C mixed-endian from the DB
        print(f"  owner raw hex: {owner_hex}")
        # Try to find in _reference117
        result = conn.execute(text(f"""
            SELECT encode(_idrref, 'hex') AS id, _code
            FROM _reference117
            WHERE encode(_idrref, 'hex') = '{owner_hex}'
            LIMIT 1
        """)).fetchone()
        if result:
            print(f"  FOUND in _reference117: _code={result[1]}")
        else:
            print("  NOT found in _reference117")
            
            # Try _reference53 too
            result2 = conn.execute(text(f"""
                SELECT encode(_idrref, 'hex') AS id, _code
                FROM _reference53
                WHERE encode(_idrref, 'hex') = '{owner_hex}'
                LIMIT 1
            """)).fetchone()
            if result2:
                print(f"  FOUND in _reference53: _code={result2[1]}")
            else:
                print("  NOT found in _reference53 either")

    # 3. Test rref resolution: _fld131rref in _reference117
    print("\n=== _reference117 _fld131rref sample ===")
    rows = conn.execute(text("""
        SELECT encode(_fld131rref, 'hex') AS rref
        FROM _reference117
        WHERE _fld131rref IS NOT NULL AND length(_fld131rref) = 16
        LIMIT 3
    """)).fetchall()
    if rows:
        sample_rref = rows[0][0]
        print(f"  sample _fld131rref hex: {sample_rref}")
        # This is a standard UUID (not 1C mixed-endian, since it's _rref not _idrref)
        # Convert to standard UUID format
        if len(sample_rref) == 32:
            std_uuid = (
                f"{sample_rref[0:8]}-{sample_rref[8:12]}-"
                f"{sample_rref[12:16]}-{sample_rref[16:20]}-{sample_rref[20:32]}"
            )
            print(f"  standard UUID: {std_uuid}")
        
        # Try to find in _reference53._idrref (convert std -> 1C mixed-endian)
        if len(sample_rref) == 32:
            # _rref stores standard UUID, need to convert to 1C for _IDRRef match
            idrref_hex = _uuid_to_1c_idrref_hex(sample_rref.lower())
            print(f"  1C _idrref hex: {idrref_hex}")
            
            result3 = conn.execute(text(f"""
                SELECT encode(_idrref, 'hex') AS id, _code
                FROM _reference53
                WHERE encode(_idrref, 'hex') = '{idrref_hex}'
                LIMIT 1
            """)).fetchone()
            if result3:
                print(f"  FOUND in _reference53: _code={result3[1]}")
            else:
                print("  NOT found in _reference53")

    # 4. Check _fld224 column type
    print("\n=== _document209 _fld224 type ===")
    cols = conn.execute(text("""
        SELECT column_name, data_type, ordinal_position
        FROM information_schema.columns
        WHERE LOWER(table_name) = '_document209'
        ORDER BY ordinal_position
    """)).fetchall()
    for c in cols:
        print(f"  {c[0]:25s} {c[1]:25s} pos={c[2]}")

    # 5. Check _fld247 (bytea column — could be rtref, type, etc)
    print("\n=== _document209 _fld247 details ===")
    rows = conn.execute(text("""
        SELECT encode(_fld247, 'hex') AS val
        FROM _document209
        WHERE _fld247 IS NOT NULL AND length(_fld247) > 0
        LIMIT 3
    """)).fetchall()
    for r in rows:
        h = r[0]
        print(f"  _fld247 hex ({len(h)} chars): {h}")

eng.dispose()
