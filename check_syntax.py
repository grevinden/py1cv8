import ast
import sys

path = r"b:\py1cv8\src\py1cv8\db_compare.py"
data = open(path, "rb").read()
print("Has BOM:", data[:3] == b"\xef\xbb\xbf")
print("First 50 bytes:", data[:50])
print("File size:", len(data))

for enc in ["utf-8-sig", "utf-8", "cp1251"]:
    try:
        text = data.decode(enc)
        print(f"{enc}: decode OK")
        try:
            ast.parse(text)
            print(f"{enc}: ast.parse OK")
            sys.exit(0)
        except SyntaxError as e:
            print(f"{enc}: syntax error at line {e.lineno}, col {e.offset}: {e.msg}")
            lines = text.splitlines()
            if e.lineno and 1 <= e.lineno <= len(lines):
                start = max(0, e.lineno - 3)
                end = min(len(lines), e.lineno + 2)
                for i in range(start, end):
                    marker = ">>>" if i == e.lineno - 1 else "   "
                    print(f"{marker} {i+1}: {repr(lines[i])}")
    except Exception as ex:
        print(f"{enc}: decode error: {ex}")
