import re

path = r"b:\py1cv8\src\py1cv8\db_compare.py"
data = open(path, "r", encoding="utf-8").read()

# Find all triple-quote positions
pattern = re.compile(r'"""')
positions = [(m.start(), m.end()) for m in pattern.finditer(data)]

# Find line number for each position
lines_before = data[:259].split("\n")
print(f"Total lines before 259: {len(lines_before)}")

# Count triple quotes in each line
line_text = data.split("\n")
print(f"Total lines: {len(line_text)}")
print()

for i, line in enumerate(line_text):
    count = line.count('"""')
    if count > 0:
        print(f"Line {i+1} ({count}x): {line.strip()[:80]}")

print()
print(f"Total triple-quote occurrences: {len(positions)}")
# They should be even
if len(positions) % 2 != 0:
    print("ODD number of triple-quotes! Last unmatched:")
    last = positions[-1]
    ln = data[:last[0]].count("\n") + 1
    print(f"  Position {last[0]}, Line {ln}")
else:
    print("Even number — but maybe nesting is wrong")
