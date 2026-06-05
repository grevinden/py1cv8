"""Check Document209 rref values."""
from sqlalchemy import create_engine, text

url = "postgresql+psycopg2://postgres@localhost:5433/MessageCenter"
eng = create_engine(url, execution_options={"isolation_level": "AUTOCOMMIT"})

with eng.connect() as c:
    rows = c.execute(text("""
        SELECT 
            count(*) as total,
            count(_fld222rref) as n_222,
            count(_fld246rref) as n_246,
            sum(CASE WHEN _fld222rref IS NOT NULL AND encode(_fld222rref, 'hex') = '00000000000000000000000000000000' THEN 1 ELSE 0 END) as zero_222,
            sum(CASE WHEN _fld246rref IS NOT NULL AND encode(_fld246rref, 'hex') = '00000000000000000000000000000000' THEN 1 ELSE 0 END) as zero_246
        FROM _document209
    """)).fetchone()
    print(f"total={rows[0]}, n_222={rows[1]}, n_246={rows[2]}, zero_222={rows[3]}, zero_246={rows[4]}")

    # Show actual values
    print("\nSample _fld222rref:")
    for r in c.execute(text("SELECT encode(_fld222rref, 'hex') FROM _document209 WHERE _fld222rref IS NOT NULL LIMIT 10")).fetchall():
        print(f"  {r[0]}")

    print("\nSample _fld246rref:")
    for r in c.execute(text("SELECT encode(_fld246rref, 'hex') FROM _document209 WHERE _fld246rref IS NOT NULL LIMIT 10")).fetchall():
        print(f"  {r[0]}")

eng.dispose()
