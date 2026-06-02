"""Analyze all metadata types across all sources."""
import zlib
import re
import psycopg2
from pathlib import Path

DB_CONFIG = dict(host="localhost", port=5433, user="postgres", password="qwaseD12")

def get_dbnames_type_names(dbname: str) -> set[str]:
    conn = psycopg2.connect(**DB_CONFIG, dbname=dbname)
    cur = conn.cursor()
    
    # Find params table
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_name ILIKE '%param%'")
    rows = cur.fetchall()
    if not rows:
        print(f"  No params table in {dbname}")
        conn.close()
        return set()
    params_table = rows[0][0]
    
    cur.execute(f'SELECT params FROM "{params_table}" WHERE id = 0')
    row = cur.fetchone()
    conn.close()
    if not row:
        print(f"  No row in {dbname}.{params_table}")
        return set()
    
    blob = bytes(row[0])
    try:
        decompressed = zlib.decompress(blob, wbits=-15)
    except Exception as e:
        print(f"  Decompress error: {e}")
        return set()
    
    text = decompressed.decode("utf-8", errors="replace")
    pattern = re.compile(r'\{"([^"]+)","([^"]+)",(\d+)\}')
    names = set()
    for m in pattern.finditer(text):
        names.add(m.group(2))
    return names


mc_names = get_dbnames_type_names("MessageCenter")
print("=== MessageCenter DBNames type_names ===")
for n in sorted(mc_names):
    print(f"  {n}")

test_names = get_dbnames_type_names("test")
print("\n=== test DBNames type_names ===")
for n in sorted(test_names):
    print(f"  {n}")

only_test = test_names - mc_names
if only_test:
    print(f"\n=== Only in test ({len(only_test)}) ===")
    for n in sorted(only_test):
        print(f"  {n}")

only_mc = mc_names - test_names
if only_mc:
    print(f"\n=== Only in MessageCenter ({len(only_mc)}) ===")
    for n in sorted(only_mc):
        print(f"  {n}")

# ── XML export ──
export_dir = Path(r"B:\py1cv8\.export_from_1c")
print("\n=== XML export directories ===")
for d in sorted(export_dir.iterdir()):
    if d.is_dir() and not d.name.startswith("."):
        xml_count = len(list(d.glob("*.xml")))
        print(f"  {d.name:35s} {xml_count} XML")

test_export = export_dir / "test_database"
if test_export.exists():
    print("\n=== test_database XML directories ===")
    for d in sorted(test_export.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
            xml_count = len(list(d.glob("*.xml")))
            print(f"  {d.name:35s} {xml_count} XML")

# ── Known mapping ──
TYPE_NAME_TO_CATEGORY = {
    "Reference": "Catalogs",
    "Document": "Documents",
    "InfoRg": "InformationRegisters",
    "Chrc": "ChartsOfCharacteristicTypes",
    "Const": "Constants",
    "Enum": "Enums",
    "AccRg": "AccumulationRegisters",
    "AccRgT": "AccumulationRegisters",
    "CalcRg": "AccountingRegisters",
    "CalcRgT": "AccountingRegisters",
    "BusinessProcess": "BusinessProcesses",
    "Task": "Tasks",
    "ExchangePlan": "ExchangePlans",
    "Sequence": "Sequences",
    "ScheduledJobs": "ScheduledJobs"
}

all_names = mc_names | test_names
print(f"\n=== All {len(all_names)} DBNames type_names ===")
for n in sorted(all_names):
    cat = TYPE_NAME_TO_CATEGORY.get(n, "???")
    print(f"  {n:25s} → {cat}")

uncategorized = [n for n in sorted(all_names) if n not in TYPE_NAME_TO_CATEGORY]
print(f"\n=== UNCATEGORIZED type_names ({len(uncategorized)}) ===")
for n in uncategorized:
    print(f"  {n}")
