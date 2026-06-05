"""Find correct UUIDs from context for the graph example."""
import json
from py1cv8.context import build_llm_context

url = "postgresql+psycopg2://postgres@localhost:5433/MessageCenter"
ctx = build_llm_context(url)

# Find objects matching the user's description
targets = [
    "ТемыУведомлений",  # _Reference147
    "ПодпискиНаУведомления",  # _InfoRg148
    "КаналыОтправкиУведомлений",  # _Reference132
    "ПротоколыОтправкиУведомлений",  # _Reference117
    "Алгоритмы",  # _Reference53
    "ЗначенияПараметровОтправкиУведомлений",  # _InfoRg119
    "РасписаниеАктивностиОбъектов",  # _InfoRg144
    "Уведомления",  # _Document209
    "ПараметрыОтправкиУведомлений",  # _ChrcSinF210
    "ЗашифрованныеДанные",  # _Reference127
    "КлючШифрования",  # _Const155
    "АдресТерминатораШифрования",  # _Const248
]

for t in targets:
    t_lower = t.lower()
    match = None
    for o in ctx["objects"]:
        tech = (o.get("tech_name") or "").lower()
        if t_lower in tech:
            match = o
            break
        for dn in (o.get("display_names") or {}).values():
            if t_lower in dn.lower():
                match = o
                break
    if match:
        print(f"{t}: uuid={match['uuid']}, table={match.get('table_name')}, tech_name={match.get('tech_name')}")
    else:
        print(f"{t}: NOT FOUND")
