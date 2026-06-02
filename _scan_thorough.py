"""
Thorough scan: try ALL decompress methods, also scan MOXCEL headers,
and scan ALL partno values for type_nums. Map each type_num to
DBNames type_name via cross-reference.
"""
import sys, io, zlib, re, struct
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import psycopg2

DB_CONFIG = dict(host="localhost", port=5433, user="postgres", password="qwaseD12")

def try_decompress(data: bytes) -> bytes | None:
    for wbits in (-15, 15, 31, 47, -9, -13):
        try:
            return zlib.decompress(data, wbits=wbits)
        except Exception:
            continue
    return None

for dbname in ("test", "MessageCenter"):
    conn = psycopg2.connect(**DB_CONFIG, dbname=dbname)
    cur = conn.cursor()

    print(f"\n{'='*60}")
    print(f"  DB: {dbname}")
    print(f"{'='*60}")

    # Get all config tables
    cur.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' "
        "AND table_name IN ('config', 'configcas')"
    )
    config_tables = [r[0] for r in cur.fetchall()]

    all_tnums = {}  # type_num -> source info

    for tbl in config_tables:
        try:
            cur.execute(
                f"SELECT filename, partno, length(binarydata) as sz "
                f"FROM {tbl} WHERE binarydata IS NOT NULL "
                f"ORDER BY filename, partno"
            )
        except Exception as e:
            print(f"  Error reading {tbl}: {e}")
            continue

        rows = cur.fetchall()
        print(f"\n  {tbl}: {len(rows)} rows total")

        # Only scan partno=0 entries (metadata header)
        p0_rows = [(fn, pn, sz) for fn, pn, sz in rows if pn == 0]
        print(f"  partno=0 entries: {len(p0_rows)}")

        for fname, partno, sz in p0_rows:
            cur.execute(
                f"SELECT binarydata FROM {tbl} WHERE filename = %s AND partno = %s",
                (fname, partno)
            )
            raw = cur.fetchone()
            if not raw or not raw[0]:
                continue
            blob = bytes(raw[0])

            tnum = None

            # Method 1: Try {1,{type_num pattern
            dec = try_decompress(blob)
            if dec:
                m = re.search(rb'\{1,\s*\n?\{(\d+)', dec[:2000])
                if m:
                    tnum = int(m.group(1))

            # Method 2: Try MOXCEL header
            if tnum is None and blob[:6] == b'MOXCEL':
                if len(blob) >= 14:
                    tnum = struct.unpack('<H', blob[11:13])[0]

            # Method 3: Try just {1,{ without newline in raw bytes
            if tnum is None:
                m = re.search(rb'\{1,\{(\d+)', blob[:2000])
                if m:
                    tnum = int(m.group(1))

            if tnum is not None and tnum <= 99:
                # Get display name from decompressed text
                tech = "?"
                disp = "?"
                if dec:
                    try:
                        text = dec.decode("utf-8", errors="replace").lstrip("\ufeff")
                        uuid_m = re.search(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', text)
                        after = text[uuid_m.end():] if uuid_m else text[:500]
                        nm = re.search(r'"([^"]{2,120})"', after[:500])
                        if nm:
                            tech = nm.group(1)
                        dm = re.search(r'"ru","([^"]{1,300})"', after[:600])
                        if dm:
                            disp = dm.group(1)
                    except Exception:
                        pass

                key = (tnum, fname)
                if key not in all_tnums:
                    all_tnums[key] = (tech, disp, tbl, sz)

        conn.close()

    # Show unique type_nums
    by_tnum = {}
    for (tnum, fname), (tech, disp, tbl, sz) in all_tnums.items():
        by_tnum.setdefault(tnum, []).append((tech, disp, tbl, sz, fname))

    print(f"\n  ALL type_nums found:")
    for tnum in sorted(by_tnum):
        entries = by_tnum[tnum]
        # Show first entry details
        e = entries[0]
        print(f"    type={tnum:3d}: count={len(entries):3d}  tech=\"{e[0]:35s}\"  sz={e[3]:6d}  tbl={e[2]}")

    # Special highligh for unknown types
    known = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 12, 16, 17, 19, 20, 22,
             33, 34, 40, 57, 68, 26, 30, 37, 14, 13}
    unknown = set(by_tnum.keys()) - known
    if unknown:
        print(f"\n  UNKNOWN type_nums: {sorted(unknown)}")
        for tnum in sorted(unknown):
            for e in by_tnum[tnum][:2]:
                print(f"    {tnum}: tech=\"{e[0]:35s}\"  sz={e[3]:6d}  tbl={e[2]}  file={e[4]}")
    else:
        print(f"\n  All type_nums accounted for ✅")
