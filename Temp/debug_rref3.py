"""Debug: check if rref UUIDs are real."""
from sqlalchemy import create_engine, text

url = "postgresql+psycopg2://postgres@localhost:5433/MessageCenter"
eng = create_engine(url, execution_options={"isolation_level": "AUTOCOMMIT"})

with eng.connect() as c:
    # Check for NULL or zeros
    rows = c.execute(text("""
        SELECT 
            count(*) as total,
            count(_fld149rref) as non_null_149,
            count(_fld150rref) as non_null_150,
            sum(CASE WHEN _fld149rref IS NOT NULL AND length(_fld149rref) = 16 AND encode(_fld149rref, 'hex') = '00000000000000000000000000000000' THEN 1 ELSE 0 END) as zero_149,
            sum(CASE WHEN _fld150rref IS NOT NULL AND length(_fld150rref) = 16 AND encode(_fld150rref, 'hex') = '00000000000000000000000000000000' THEN 1 ELSE 0 END) as zero_150
        FROM _inforg148
    """)).fetchone()

    print(f"total={rows[0]}, non_null_149={rows[1]}, non_null_150={rows[2]}, zero_149={rows[3]}, zero_150={rows[4]}")

    # Show sample rref values
    print("\nSample _fld149rref values:")
    rows = c.execute(text("""
        SELECT encode(_fld149rref, 'hex')
        FROM _inforg148
        WHERE _fld149rref IS NOT NULL AND length(_fld149rref) = 16
        LIMIT 10
    """)).fetchall()
    for r in rows:
        print(f"  {r[0]}")

    print("\nSample _fld150rref values:")
    rows = c.execute(text("""
        SELECT encode(_fld150rref, 'hex')
        FROM _inforg148
        WHERE _fld150rref IS NOT NULL AND length(_fld150rref) = 16
        LIMIT 10
    """)).fetchall()
    for r in rows:
        print(f"  {r[0]}")

    # Check _owneridrref sample values for comparison
    print("\nSample _owneridrref in _reference132:")
    rows = c.execute(text("""
        SELECT encode(_owneridrref, 'hex')
        FROM _reference132
        WHERE _owneridrref IS NOT NULL
        LIMIT 3
    """)).fetchall()
    for r in rows:
        print(f"  {r[0]}")

eng.dispose()
