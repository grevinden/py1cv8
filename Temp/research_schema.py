"""Research DB format for graph: owner, parent, rref targets."""
import json
from sqlalchemy import create_engine, text
from py1cv8.context import build_llm_context

url = "postgresql+psycopg2://postgres@localhost:5433/MessageCenter"
ctx = build_llm_context(url)

eng = create_engine(url)

with eng.connect() as conn:
    # 1. Check _reference147 (ТемыУведомлений) for _owneridrref / _parentidrref
    print("=== _reference147 columns ===")
    cols = conn.execute(text("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE LOWER(table_name) = '_reference147'
        ORDER BY ordinal_position
    """)).fetchall()
    for c in cols:
        print(f"  {c[0]:30s} {c[1]}")

    # 2. Check _reference132 (КаналыОтправкиУведомлений) for owner
    print("\n=== _reference132 columns ===")
    cols = conn.execute(text("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE LOWER(table_name) = '_reference132'
        ORDER BY ordinal_position
    """)).fetchall()
    for c in cols:
        print(f"  {c[0]:30s} {c[1]}")

    # 3. Check _reference117 (ПротоколыОтправкиУведомлений)
    print("\n=== _reference117 columns ===")
    cols = conn.execute(text("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE LOWER(table_name) = '_reference117'
        ORDER BY ordinal_position
    """)).fetchall()
    for c in cols:
        print(f"  {c[0]:30s} {c[1]}")

    # 4. Check _document209 (Уведомления)
    print("\n=== _document209 columns ===")
    cols = conn.execute(text("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE LOWER(table_name) = '_document209'
        ORDER BY ordinal_position
    """)).fetchall()
    for c in cols:
        print(f"  {c[0]:30s} {c[1]}")

    # 5. Check _vt254 (tabular section of _document209)
    print("\n=== _vt254 columns ===")
    cols = conn.execute(text("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE LOWER(table_name) = '_vt254'
        ORDER BY ordinal_position
    """)).fetchall()
    for c in cols:
        print(f"  {c[0]:30s} {c[1]}")

    # 6. Check _chrcsinf210 (ПараметрыОтправкиУведомлений)
    print("\n=== _chrcsinf210 columns ===")
    cols = conn.execute(text("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE LOWER(table_name) = '_chrcsinf210'
        ORDER BY ordinal_position
    """)).fetchall()
    for c in cols:
        print(f"  {c[0]:30s} {c[1]}")

    # 7. Sample data from _reference132 to see owner
    print("\n=== _reference132 sample (_description, _owneridrref) ===")
    rows = conn.execute(text("""
        SELECT _description, encode(_owneridrref, 'hex') AS owner
        FROM _reference132 LIMIT 5
    """)).fetchall()
    for r in rows:
        print(f"  desc={r[0]}, owner_hex={r[1]}")

eng.dispose()
