# -*- coding: utf-8 -*-
"""Очистка уже извлечённых .bsl — оставить толькоProcedure/Function блоки."""
import os, re

out_dir = r'B:\py1cv8\modules_v3'

def extract_bsl_blocks(text):
    """Извлечь только полные Procedure/Function блоки из текста."""
    blocks = []
    # Match Процедура ... КонецПроцедуры or Функция ... КонецФункции (with directives before)
    pattern = r'''(&НаКлиенте\s*|&НаСервере\s*|&НаКлиентеИНаСервере\s*)?([\s\S]*?)(Процедура\s+\w+[\r\n]+(?:[\s\S]*?)?\n\t?КонецПроцедуры)'''
    pattern2 = r'''(&НаКлиенте\s*|&НаСервере\s*|&НаКлиентеИНаСервере\s*)?([\s\S]*?)(Функция\s+\w+[\r\n]+(?:[\s\S]*?)?\n\t?КонецФункции)'''

    for pat in [pattern, pattern2]:
        for m in re.finditer(pat, text):
            directive = m.group(1) or ''
            between = m.group(2).strip()
            body = m.group(3)
            block = f"{directive}\n{between}\n{body}".strip() + '\n'
            blocks.append(block)

    return blocks


for fname in sorted(os.listdir(out_dir)):
    if not fname.endswith('.bsl'):
        continue
    fpath = os.path.join(out_dir, fname)
    with open(fpath, 'r', encoding='utf-8') as f:
        text = f.read()

    # Check if file has trailing garbage (serialized structure markers)
    has_garbage = bool(re.search(r'\{[0-9a-fA-F\-]+,\s*\{"', text))

    if not has_garbage:
        print(f"  OK: {fname} (already clean)")
        continue

    # Extract only valid BSL blocks
    blocks = extract_bsl_blocks(text)

    if blocks:
        clean_text = '\n'.join(blocks).strip() + '\n'
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(clean_text)
        print(f"CLEANED: {fname} -> {len(blocks)} block(s), {len(clean_text)} chars")
    else:
        # Fallback: cut at last КонецПроцедуры/КонецФункции
        for kw in ['КонецПроцедуры\n', 'КонецФункции\n']:
            idx = text.rfind(kw)
            if idx >= 0:
                clean_text = text[:idx + len(kw)].strip() + '\n'
                with open(fpath, 'w', encoding='utf-8') as f:
                    f.write(clean_text)
                print(f"FALLBACK CLEANED: {fname} -> cut at '{kw.strip()}'")
                break
        else:
            print(f"  SKIP (no BSL blocks found): {fname}")

print("\nDone.")
