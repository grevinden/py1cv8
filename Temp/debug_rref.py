"""Debug rref UUID resolution."""
from sqlalchemy import create_engine, text
from py1cv8.resolve_uuid import _uuid_to_1c_idrref_hex

url = "postgresql+psycopg2://postgres@localhost:5433/MessageCenter"
eng = create_engine(url)

with eng.connect() as c:
    # Sample UUID from _fld149rref
    rows = c.execute(text("""
        SELECT encode(_fld149rref, 'hex')
        FROM _inforg148
        WHERE _fld149rref IS NOT NULL AND length(_fld149rref) = 16
        LIMIT 1
    """)).fetchall()

    for r in rows:
        std_hex = r[0]
        print(f"Standard hex: {std_hex}")
        idrref_hex = _uuid_to_1c_idrref_hex(std_hex)
        print(f"1C _idrref hex: {idrref_hex}")

        # Check all reference tables
        nums = [53, 54, 55, 85, 107, 108, 117, 132, 147]
        for n in nums:
            try:
                result = c.execute(text(
                    f"SELECT 1 FROM _reference{n}"
                    f" WHERE encode(_IDRRef, 'hex') = :h LIMIT 1"
                ), {"h": idrref_hex}).fetchone()
                if result:
                    print(f"!!! Found in _reference{n} !!!")
            except Exception as e:
                pass

        # Also check _document209
        result = c.execute(text(
            "SELECT 1 FROM _document209"
            " WHERE encode(_IDRRef, 'hex') = :h LIMIT 1"
        ), {"h": idrref_hex}).fetchone()
        if result:
            print("!!! Found in _document209 !!!")

    # Check second rref
    rows2 = c.execute(text("""
        SELECT encode(_fld150rref, 'hex')
        FROM _inforg148
        WHERE _fld150rref IS NOT NULL AND length(_fld150rref) = 16
        LIMIT 1
    """)).fetchall()

    for r in rows2:
        std_hex = r[0]
        print(f"\nSecond rref standard hex: {std_hex}")
        idrref_hex = _uuid_to_1c_idrref_hex(std_hex)
        print(f"1C _idrref hex: {idrref_hex}")

        nums = [53, 54, 55, 85, 107, 108, 117, 132, 147]
        for n in nums:
            try:
                result = c.execute(text(
                    f"SELECT 1 FROM _reference{n}"
                    f" WHERE encode(_IDRRef, 'hex') = :h LIMIT 1"
                ), {"h": idrref_hex}).fetchone()
                if result:
                    print(f"!!! Found in _reference{n} !!!")
            except Exception as e:
                pass

eng.dispose()
