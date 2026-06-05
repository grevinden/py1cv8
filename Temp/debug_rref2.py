"""Debug rref UUID resolution with autocommit."""
from sqlalchemy import create_engine, text
from py1cv8.resolve_uuid import _uuid_to_1c_idrref_hex

url = "postgresql+psycopg2://postgres@localhost:5433/MessageCenter"
eng = create_engine(url, execution_options={"isolation_level": "AUTOCOMMIT"})

with eng.connect() as c:
    # List all tables with _IDRRef
    tables = c.execute(text("""
        SELECT LOWER(table_name) FROM information_schema.columns
        WHERE LOWER(column_name) = '_idrref'
        ORDER BY table_name
    """)).fetchall()

    table_names = [r[0] for r in tables]
    print("Tables with _IDRRef:")
    for tn in table_names:
        print(f"  {tn}")

    # Sample UUID from _fld149rref
    rows = c.execute(text("""
        SELECT encode(_fld149rref, 'hex')
        FROM _inforg148
        WHERE _fld149rref IS NOT NULL AND length(_fld149rref) = 16
        LIMIT 1
    """)).fetchall()

    for r in rows:
        std_hex = r[0]
        print(f"\nStandard hex from _fld149rref: {std_hex}")
        idrref_hex = _uuid_to_1c_idrref_hex(std_hex)
        print(f"1C _idrref hex: {idrref_hex}")

        # Try all tables
        for tn in table_names[:20]:
            try:
                result = c.execute(text(
                    f"SELECT 1 FROM {tn}"
                    f" WHERE encode(_IDRRef, 'hex') = :h LIMIT 1"
                ), {"h": idrref_hex}).fetchone()
                if result:
                    print(f"!!! Found in {tn} !!!")
            except Exception as e:
                print(f"  Error on {tn}: {e}")

    # Second rref
    rows2 = c.execute(text("""
        SELECT encode(_fld150rref, 'hex')
        FROM _inforg148
        WHERE _fld150rref IS NOT NULL AND length(_fld150rref) = 16
        LIMIT 1
    """)).fetchall()

    for r in rows2:
        std_hex2 = r[0]
        print(f"\nSecond rref standard hex: {std_hex2}")
        idrref_hex2 = _uuid_to_1c_idrref_hex(std_hex2)
        print(f"1C _idrref hex: {idrref_hex2}")

        for tn in table_names[:20]:
            try:
                result = c.execute(text(
                    f"SELECT 1 FROM {tn}"
                    f" WHERE encode(_IDRRef, 'hex') = :h LIMIT 1"
                ), {"h": idrref_hex2}).fetchone()
                if result:
                    print(f"!!! Found in {tn} !!!")
            except:
                pass

eng.dispose()
