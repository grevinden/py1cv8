import sys

path = r"b:\py1cv8\src\py1cv8\db_compare.py"
data = open(path, "rb").read()

lines = data.split(b"\n")
for i in range(253, min(275, len(lines))):
    line = lines[i]
    # Show raw bytes for triple-quote areas
    print(f"Line {i+1}: {line}")
    # Check for smart quotes / weird chars
    for j, b in enumerate(line):
        if b > 127:
            print(f"  Non-ASCII at byte {j}: 0x{b:02x}")
    # Check triple quotes
    pos = 0
    while True:
        idx = line.find(b'"""', pos)
        if idx == -1:
            break
        print(f"  Found triple-quote at byte {idx}")
        pos = idx + 3
