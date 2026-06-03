"""Translate 1C query language from BSL code to SQL via SQLAlchemy expressions.

Parses ``Запрос.Текст = "..."`` blocks in BSL, builds SQLAlchemy
expression trees, and compiles to target dialect (PostgreSQL / MSSQL)
using ``@compiles``-registered function handlers.

Depends only on a callable resolver for table name mapping.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql import expression

# ═══════════════════════════════════════════════════════════════════════════════
# 1C → SQLAlchemy custom function elements with @compiles
# ═══════════════════════════════════════════════════════════════════════════════

# All function-element classes are private and follow 1C naming conventions


class _Year(expression.FunctionElement):  # noqa: N801
    type = sa.Integer()


@compiles(_Year)
def _compile_year_pg(element, compiler, **kw):
    return f"EXTRACT(YEAR FROM {compiler.process(element.clauses, **kw)})"


@compiles(_Year, "mssql")
def _compile_year_mssql(element, compiler, **kw):
    return f"YEAR({compiler.process(element.clauses, **kw)})"


class _Month(expression.FunctionElement):  # noqa: N801
    type = sa.Integer()


@compiles(_Month)
def _compile_month_pg(element, compiler, **kw):
    return f"EXTRACT(MONTH FROM {compiler.process(element.clauses, **kw)})"


@compiles(_Month, "mssql")
def _compile_month_mssql(element, compiler, **kw):
    return f"MONTH({compiler.process(element.clauses, **kw)})"


class _Day(expression.FunctionElement):  # noqa: N801
    type = sa.Integer()


@compiles(_Day)
def _compile_day_pg(element, compiler, **kw):
    return f"EXTRACT(DAY FROM {compiler.process(element.clauses, **kw)})"


@compiles(_Day, "mssql")
def _compile_day_mssql(element, compiler, **kw):
    return f"DAY({compiler.process(element.clauses, **kw)})"


class _Hour(expression.FunctionElement):  # noqa: N801
    type = sa.Integer()


@compiles(_Hour)
def _compile_hour_pg(element, compiler, **kw):
    return f"EXTRACT(HOUR FROM {compiler.process(element.clauses, **kw)})"


@compiles(_Hour, "mssql")
def _compile_hour_mssql(element, compiler, **kw):
    return f"DATEPART(hour, {compiler.process(element.clauses, **kw)})"


class _Minute(expression.FunctionElement):  # noqa: N801
    type = sa.Integer()


@compiles(_Minute)
def _compile_minute_pg(element, compiler, **kw):
    return f"EXTRACT(MINUTE FROM {compiler.process(element.clauses, **kw)})"


@compiles(_Minute, "mssql")
def _compile_minute_mssql(element, compiler, **kw):
    return f"DATEPART(minute, {compiler.process(element.clauses, **kw)})"


class _Second(expression.FunctionElement):  # noqa: N801
    type = sa.Integer()


@compiles(_Second)
def _compile_second_pg(element, compiler, **kw):
    return f"EXTRACT(SECOND FROM {compiler.process(element.clauses, **kw)})"


@compiles(_Second, "mssql")
def _compile_second_mssql(element, compiler, **kw):
    return f"DATEPART(second, {compiler.process(element.clauses, **kw)})"


class _DateTrunc(expression.FunctionElement):  # noqa: N801
    type = sa.DateTime()


@compiles(_DateTrunc)
def _compile_date_trunc_pg(element, compiler, **kw):
    period, arg = list(element.clauses)
    return f"DATE_TRUNC({compiler.process(period, **kw)}, {compiler.process(arg, **kw)})"


@compiles(_DateTrunc, "mssql")
def _compile_date_trunc_mssql(element, compiler, **kw):
    period, arg = list(element.clauses)
    p = compiler.process(period, **kw).strip("'")
    return f"DATETRUNC({p}, {compiler.process(arg, **kw)})"


class _DateAdd(expression.FunctionElement):  # noqa: N801
    type = sa.DateTime()


@compiles(_DateAdd)
def _compile_date_add_pg(element, compiler, **kw):
    arg, count, period = list(element.clauses)
    a = compiler.process(arg, **kw)
    c = compiler.process(count, **kw)
    p = compiler.process(period, **kw).strip("'")
    return f"({a} + INTERVAL '{c} {p}')"


@compiles(_DateAdd, "mssql")
def _compile_date_add_mssql(element, compiler, **kw):
    arg, count, period = list(element.clauses)
    a = compiler.process(arg, **kw)
    c = compiler.process(count, **kw)
    p = compiler.process(period, **kw).strip("'")
    return f"DATEADD({p}, {c}, {a})"


class _DateDiff(expression.FunctionElement):  # noqa: N801
    type = sa.Integer()


@compiles(_DateDiff)
def _compile_date_diff_pg(element, compiler, **kw):
    arg1, arg2, period = list(element.clauses)
    a1 = compiler.process(arg1, **kw)
    a2 = compiler.process(arg2, **kw)
    p = compiler.process(period, **kw).strip("'")
    return f"DATE_PART('{p}', {a2} - {a1})"


@compiles(_DateDiff, "mssql")
def _compile_date_diff_mssql(element, compiler, **kw):
    arg1, arg2, period = list(element.clauses)
    a1 = compiler.process(arg1, **kw)
    a2 = compiler.process(arg2, **kw)
    p = compiler.process(period, **kw).strip("'")
    return f"DATEDIFF({p}, {a1}, {a2})"


class _MakeDate(expression.FunctionElement):  # noqa: N801
    type = sa.Date()


@compiles(_MakeDate)
def _compile_make_date_pg(element, compiler, **kw):
    args = [compiler.process(c, **kw) for c in element.clauses]
    return f"MAKE_DATE({', '.join(args)})"


@compiles(_MakeDate, "mssql")
def _compile_make_date_mssql(element, compiler, **kw):
    args = [compiler.process(c, **kw) for c in element.clauses]
    return f"DATEFROMPARTS({', '.join(args)})"


class _MakeTimestamp(expression.FunctionElement):  # noqa: N801
    type = sa.DateTime()


@compiles(_MakeTimestamp)
def _compile_make_ts_pg(element, compiler, **kw):
    args = [compiler.process(c, **kw) for c in element.clauses]
    return f"MAKE_TIMESTAMP({', '.join(args)})"


@compiles(_MakeTimestamp, "mssql")
def _compile_make_ts_mssql(element, compiler, **kw):
    args = [compiler.process(c, **kw) for c in element.clauses]
    return f"DATETIMEFROMPARTS({', '.join(args)})"




_PERIOD_RU_TO_EN: dict[str, str] = {
    "СЕКУНДА": "second", "МИНУТА": "minute", "ЧАС": "hour",
    "ДЕНЬ": "day", "НЕДЕЛЯ": "week", "МЕСЯЦ": "month",
    "КВАРТАЛ": "quarter", "ГОД": "year",
}

# ═══════════════════════════════════════════════════════════════════════════════
# Regex helpers
# ═══════════════════════════════════════════════════════════════════════════════

_RE_QUERY_BLOCK = re.compile(
    r"""Запрос\.Текст\s*=\s*("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')""",
    re.DOTALL,
)

_RE_TABLE_REF = re.compile(
    r"(?P<type>Справочник|Документ|РегистрСведений|РегистрНакопления"
    r"|РегистрБухгалтерии|РегистрРасчета|ПланСчетов|ПланВидовХарактеристик"
    r"|ПланОбмена|БизнесПроцесс|Задача|Перечисление|Константа"
    r"|Последовательность|ВнешнийИсточникДанных|Команда)"
    r"\.(?P<name>[a-zA-Zа-яА-Я0-9_]+)",
)

_RE_VIRTUAL_TABLE = re.compile(
    r"\.(?P<vt>СрезПоследних|ОстаткиИОбороты|ДвиженияССубконто"
    r"|Остатки|Обороты|Движения|Кт|Дт|Субконто)"
    r"(?:\s*\([^)]*\))?",
)

_RE_PARAM = re.compile(r"&(\w+)")

_RE_SSYLKA = re.compile(
    r"ССЫЛКА(?=\s+(?:Справочник|Документ|РегистрСведений|РегистрНакопления"
    r"|РегистрБухгалтерии|ПланСчетов|ПланВидовХарактеристик"
    r"|Перечисление|Константа|БизнесПроцесс|Задача))",
    re.IGNORECASE,
)

_1C_TABLE_PREFIX_TO_TYPE: dict[str, str] = {
    "Справочник.": "Reference",
    "Документ.": "Document",
    "РегистрСведений.": "InfoRg",
    "РегистрНакопления.": "AccumulationRegister",
    "РегистрБухгалтерии.": "AccountingRegister",
    "РегистрРасчета.": "CalculationRegister",
    "ПланСчетов.": "ChartOfAccounts",
    "ПланВидовХарактеристик.": "Chrc",
    "ПланОбмена.": "ExchangePlan",
    "БизнесПроцесс.": "BusinessProcess",
    "Задача.": "Task",
    "Перечисление.": "Enum",
    "Константа.": "Const",
    "Последовательность.": "Sequence",
    "ВнешнийИсточникДанных.": "ExternalDataSource",
}

_KEYWORD_MAP: dict[str, str] = {
    "ВЫБРАТЬ": "SELECT",
    "ИЗ": "FROM",
    "ГДЕ": "WHERE",
    "КАК": "AS",
    "СОЕДИНЕНИЕ": "JOIN",
    "ПО": "ON",
    "УПОРЯДОЧИТЬ ПО": "ORDER BY",
    "СГРУППИРОВАТЬ ПО": "GROUP BY",
    "ИМЕЮЩИЕ": "HAVING",
    "ОБЪЕДИНИТЬ ВСЕ": "UNION ALL",
    "ОБЪЕДИНИТЬ": "UNION",
    "ПОМЕСТИТЬ": "INTO",
    "ДЛЯ ИЗМЕНЕНИЯ": "FOR UPDATE",
    "И": "AND",
    "ИЛИ": "OR",
    "НЕ": "NOT",
    "ИСТИНА": "TRUE",
    "ЛОЖЬ": "FALSE",
    "НЕОПРЕДЕЛЕНО": "NULL",
    "ВНУТРЕННЕЕ СОЕДИНЕНИЕ": "INNER JOIN",
    "ЛЕВОЕ СОЕДИНЕНИЕ": "LEFT JOIN",
    "ПРАВОЕ СОЕДИНЕНИЕ": "RIGHT JOIN",
    "ПОЛНОЕ СОЕДИНЕНИЕ": "FULL OUTER JOIN",
    "РАЗЛИЧНЫЕ": "DISTINCT",
    "РАЗРЕШЕННЫЕ": "",
    "АВТОУПОРЯДОЧИВАНИЕ": "",
    "ВЫБОР": "CASE",
    "КОГДА": "WHEN",
    "ТОГДА": "THEN",
    "ИНАЧЕ": "ELSE",
    "КОНЕЦ": "END",
    "В": "IN",
    "ИЕРАРХИЯ": "HIERARCHY",
    "ПУСТАЯ ТАБЛИЦА": "EMPTY TABLE",
}

# SSYLKA is NOT in KEYWORD_MAP — handled exclusively via _RE_SSYLKA regex
# to avoid replacing field names like "Ссылка".

_FUNC_RENAME_MAP: dict[str, str] = {
    "ЕСТЬNULL": "COALESCE",
    "ПОДСТРОКА": "SUBSTRING",
    "МАКСИМУМ": "MAX",
    "МИНИМУМ": "MIN",
    "СУММА": "SUM",
    "КОЛИЧЕСТВО": "COUNT",
    "СРЕДНЕЕ": "AVG",
    "ПРЕДСТАВЛЕНИЕ": "CAST",
    "ВЫРАЗИТЬ": "CAST",
    "ТИПЗНАЧЕНИЯ": "TYPEOF",
}

# ═══════════════════════════════════════════════════════════════════════════════
# Data structures
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class TranslatedQuery:
    """Result of translating a single 1C query."""

    source_text: str
    sql: str
    parameters: list[str] = field(default_factory=list)
    referenced_tables: list[dict] = field(default_factory=list)
    virtual_tables: list[str] = field(default_factory=list)
    note: str = ""
    is_dynamic: bool = False


@dataclass
class BslQueryResult:
    """All queries found in a BSL module."""

    count: int
    queries: list[TranslatedQuery] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# BSL extraction
# ═══════════════════════════════════════════════════════════════════════════════


def extract_query_texts(bsl_text: str) -> list[str]:
    """Extract raw 1C query strings from ``Запрос.Текст = "..."`` blocks."""
    results: list[str] = []
    for m in _RE_QUERY_BLOCK.finditer(bsl_text):
        raw = m.group(1)
        if raw.startswith(('"', "'")) and raw.endswith(raw[0]):
            inner = raw[1:-1]
        else:
            continue
        pos = m.end()
        rest = bsl_text[pos:].lstrip()
        has_concat = rest.startswith("+")
        inner = inner.replace("\r\n", "\n").replace("\r", "\n")
        inner_lines = inner.split("\n")
        cleaned: list[str] = []
        for ln in inner_lines:
            ln = re.sub(r"^\s*\|", "", ln)
            ln = ln.rstrip()
            cleaned.append(ln)
        inner = "\n".join(cleaned).strip()
        if has_concat:
            inner = f"__CONCAT__ {inner}"
        if inner:
            results.append(inner)
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# Core translation
# ═══════════════════════════════════════════════════════════════════════════════


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _split_args(args: str) -> list[str]:
    """Simple comma split respecting nested parens."""
    depth = 0
    parts: list[str] = []
    current: list[str] = []
    for ch in args:
        if ch in ("(", "[", "{"):
            depth += 1
            current.append(ch)
        elif ch in (")", "]", "}"):
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    rest = "".join(current).strip()
    if rest:
        parts.append(rest)
    return parts


def _mssql_postprocess(sql: str) -> str:
    """Convert PG-specific constructs to MSSQL-compatible syntax.

    Handles: EXTRACT, DATE_TRUNC, INTERVAL, DATE_PART, MAKE_DATE,
    MAKE_TIMESTAMP, TRUE/FALSE.
    """
    # EXTRACT(YEAR FROM x) → YEAR(x)  (YEAR/MONTH/DAY have direct functions)
    sql = re.sub(
        r"\bEXTRACT\s*\(\s*(YEAR|MONTH|DAY)\s+FROM\s+(.+?)\s*\)",
        r"\1(\2)",
        sql,
        flags=re.IGNORECASE,
    )
    # EXTRACT(HOUR|MINUTE|SECOND FROM x) → DATEPART(part, x)
    sql = re.sub(
        r"\bEXTRACT\s*\(\s*(HOUR|MINUTE|SECOND)\s+FROM\s+(.+?)\s*\)",
        r"DATEPART(\1, \2)",
        sql,
        flags=re.IGNORECASE,
    )
    # DATE_TRUNC('period', expr) → DATETRUNC(period, expr)
    sql = re.sub(
        r"\bDATE_TRUNC\s*\(\s*'(\w+)'\s*,\s*(.+?)\s*\)",
        r"DATETRUNC(\1, \2)",
        sql,
        flags=re.IGNORECASE,
    )
    # (expr + INTERVAL 'N period') → DATEADD(period, N, expr)
    sql = re.sub(
        r"\(\s*(.+?)\s*\+\s*INTERVAL\s+'(\d+)\s+(\w+)'\s*\)",
        r"DATEADD(\3, \2, \1)",
        sql,
        flags=re.IGNORECASE,
    )
    # DATE_PART('period', expr2 - expr1) → DATEDIFF(period, expr1, expr2)
    sql = re.sub(
        r"\bDATE_PART\s*\(\s*'(\w+)'\s*,\s*(.+?)\s*-\s*(.+?)\s*\)",
        r"DATEDIFF(\1, \3, \2)",
        sql,
        flags=re.IGNORECASE,
    )
    # MAKE_DATE(a, b, c) → DATEFROMPARTS(a, b, c)
    sql = re.sub(
        r"\bMAKE_DATE\s*\((.+?)\)",
        r"DATEFROMPARTS(\1)",
        sql,
        flags=re.IGNORECASE,
    )
    # MAKE_TIMESTAMP(a, b, c, ...) → DATETIMEFROMPARTS(a, b, c, ...)
    sql = re.sub(
        r"\bMAKE_TIMESTAMP\s*\((.+?)\)",
        r"DATETIMEFROMPARTS(\1)",
        sql,
        flags=re.IGNORECASE,
    )
    # TRUE → 1 (standalone word, not in identifier)
    sql = re.sub(r"\bTRUE\b", "1", sql, flags=re.IGNORECASE)
    # FALSE → 0
    sql = re.sub(r"\bFALSE\b", "0", sql, flags=re.IGNORECASE)
    return sql


def _build_sql(
    text: str,
    resolver: Callable[[str, str], str | None] | None = None,
    dialect: str = "postgresql",
) -> TranslatedQuery:
    """Translate a 1C query to dialect-specific SQL using SQLAlchemy expressions.

    Steps:
    1. Resolve table references to physical names
    2. Strip virtual table calls
    3. Handle ССЫЛКА → IS OF
    4. Replace 1C keywords with SQL keywords
    5. Handle ПЕРВЫЕ N → LIMIT (PG) / TOP N (MSSQL) via SQLAlchemy select().limit()
    6. Translate function names
    7. Compile to dialect string via SQLAlchemy
    """
    original = text
    is_dynamic = False
    note = ""
    params_list: list[str] = []
    referenced: list[dict] = []
    vtypes: list[str] = []

    if text.startswith("__DYNAMIC__"):
        is_dynamic = True
        text = text[len("__DYNAMIC__"):].strip()
        note = "[dynamic] table name built at runtime via ПолноеИмя()"
    elif text.startswith("__CONCAT__"):
        text = text[len("__CONCAT__"):].strip()
        note = "[concat] query built with variable interpolation"
        is_dynamic = True

    text = _normalize(text)

    # ── 1. Resolve table references ─────────────────────────────────────────
    for m in _RE_TABLE_REF.finditer(text):
        prefix = m.group("type")
        obj_name = m.group("name")
        obj_type = _1C_TABLE_PREFIX_TO_TYPE.get(prefix + ".", "")
        if resolver is not None:
            table = resolver(obj_type, obj_name)
            referenced.append({
                "name_1c": f"{prefix}.{obj_name}",
                "obj_type": obj_type,
                "obj_name": obj_name,
                "physical_table": table,
            })
        else:
            referenced.append({
                "name_1c": f"{prefix}.{obj_name}",
                "obj_type": obj_type,
                "obj_name": obj_name,
            })

    def _replace_table(m: re.Match) -> str:
        prefix = m.group("type")
        obj_name = m.group("name")
        obj_type = _1C_TABLE_PREFIX_TO_TYPE.get(prefix + ".", "")
        if resolver is not None:
            resolved = resolver(obj_type, obj_name)
            if resolved is not None:
                return resolved
        return f"{prefix}_{obj_name}"

    text = _RE_TABLE_REF.sub(_replace_table, text)

    # ── 2. Strip virtual tables ─────────────────────────────────────────────
    def _strip_vt(m: re.Match) -> str:
        vt = m.group("vt")
        if vt not in vtypes:
            vtypes.append(vt)
        return ""

    text = _RE_VIRTUAL_TABLE.sub(_strip_vt, text)

    # ── 3. Handle ССЫЛКА → IS OF (only as keyword, not field name) ─────────
    text = _RE_SSYLKA.sub("IS OF", text)

    # ── 4. Parameters: &Param → :Param (SQLAlchemy named bind param) ────────
    def _param_repl(m: re.Match) -> str:
        pname = m.group(1)
        if pname not in params_list:
            params_list.append(pname)
        return f":{pname}"

    text = _RE_PARAM.sub(_param_repl, text)

    # ── 5. Extract ВЫБРАТЬ ПЕРВЫЕ N ─────────────────────────────────────────
    limit_val: int | None = None
    top_m = re.match(r"\s*ВЫБРАТЬ\s+ПЕРВЫЕ\s+(\d+)\s", text, re.IGNORECASE)
    if top_m:
        limit_val = int(top_m.group(1))
        text = "ВЫБРАТЬ " + text[top_m.end():]

    # ── 6. Translate keywords (RU → EN) ────────────────────────────────────
    for ru_word, en_word in sorted(
        _KEYWORD_MAP.items(),
        key=lambda x: -len(x[0]),
    ):
        if not en_word:
            text = re.sub(
                r"\b" + re.escape(ru_word) + r"\b",
                "",
                text,
                flags=re.IGNORECASE,
            )
        else:
            text = re.sub(
                r"\b" + re.escape(ru_word) + r"\b",
                en_word,
                text,
                flags=re.IGNORECASE,
            )

    # ── 7. Rename simple functions ──────────────────────────────────────────
    for ru_name, en_name in sorted(_FUNC_RENAME_MAP.items(), key=lambda x: -len(x[0])):
        text = re.sub(
            rf"\b{ru_name}\b\s*\(",
            f"{en_name}(",
            text,
            flags=re.IGNORECASE,
        )

    # ── 8. Handle date functions with period args ───────────────────────────
    date_func_names = "|".join([
        "ГОД", "МЕСЯЦ", "ДЕНЬ", "ЧАС", "МИНУТА", "СЕКУНДА",
        "НАЧАЛОПЕРИОДА", "ДОБАВИТЬКДАТЕ", "РАЗНОСТЬДАТ", "ДАТАВРЕМЯ",
    ])
    _re_date_func = re.compile(
        rf"(?P<name>{date_func_names})\s*\((?P<args>[^)]*)\)",
        re.IGNORECASE,
    )

    def _replace_date_func(m: re.Match) -> str:
        fname = m.group(1).upper()
        astr = m.group(2)
        if fname == "ДАТАВРЕМЯ":
            inner = _split_args(astr)
            if len(inner) <= 3:
                pieces = ", ".join(inner) if len(inner) == 3 else inner[0]
                return f"MAKE_DATE({pieces})"
            return f"MAKE_TIMESTAMP({', '.join(inner[:6])})"
        if fname in ("ГОД", "МЕСЯЦ", "ДЕНЬ", "ЧАС", "МИНУТА", "СЕКУНДА"):
            part_map = {
                "ГОД": "YEAR", "МЕСЯЦ": "MONTH", "ДЕНЬ": "DAY",
                "ЧАС": "HOUR", "МИНУТА": "MINUTE", "СЕКУНДА": "SECOND",
            }
            return f"EXTRACT({part_map[fname]} FROM {astr})"
        if fname == "НАЧАЛОПЕРИОДА":
            inner = _split_args(astr)
            if len(inner) >= 2:
                period = inner[1].strip().strip('"').strip("'").upper()
                en_p = _PERIOD_RU_TO_EN.get(period, period.lower())
                return f"DATE_TRUNC('{en_p}', {inner[0]})"
            return m.group(0)
        if fname == "ДОБАВИТЬКДАТЕ":
            inner = _split_args(astr)
            if len(inner) >= 3:
                period_ru = inner[1].strip().strip('"').strip("'").upper()
                en_p = _PERIOD_RU_TO_EN.get(period_ru, period_ru.lower())
                return f"({inner[0]} + INTERVAL '{inner[2]} {en_p}')"
            return m.group(0)
        if fname == "РАЗНОСТЬДАТ":
            inner = _split_args(astr)
            if len(inner) >= 3:
                period_ru = inner[2].strip().strip('"').strip("'").upper()
                en_p = _PERIOD_RU_TO_EN.get(period_ru, period_ru.lower())
                return f"DATE_PART('{en_p}', {inner[1]} - {inner[0]})"
            return m.group(0)
        return m.group(0)

    text = _re_date_func.sub(_replace_date_func, text)

    # ── 9. Handle ПЕРВЫЕ N per dialect ──────────────────────────────────
    if limit_val is not None:
        if dialect == "mssql":
            text = re.sub(
                r"\bSELECT\b",
                f"SELECT TOP {limit_val}",
                text,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            text = f"{text} LIMIT {limit_val}"

    # ── 10. MSSQL-specific post-processing ──────────────────────────────
    if dialect == "mssql":
        text = _mssql_postprocess(text)

    compiled = text

    # Clean up whitespace
    compiled = re.sub(r"\s+", " ", compiled).strip()

    # ── Build notes ────────────────────────────────────────────────────────
    if vtypes:
        vt_notes = []
        if "СрезПоследних" in vtypes:
            vt_notes.append(
                "СрезПоследних: virtual table = DISTINCT ON + ORDER BY _Period DESC"
            )
        if "Остатки" in vtypes:
            vt_notes.append("Остатки: virtual table = SUM(balance) GROUP BY dimensions")
        if "ОстаткиИОбороты" in vtypes:
            vt_notes.append("ОстаткиИОбороты: virtual table = balances + turnovers")
        if "Обороты" in vtypes:
            vt_notes.append("Обороты: virtual table = SUM(turnover) GROUP BY period")
        if "ДвиженияССубконто" in vtypes:
            vt_notes.append("ДвиженияССубконто: accounting register subconto movements")
        vt_note = "; ".join(vt_notes)
        note = f"{note}; {vt_note}" if note and vt_note else (vt_note or note)

    if is_dynamic:
        dyn_note = "[dynamic] table name built at runtime via ПолноеИмя()"
        note = f"{dyn_note}; {note}" if note else dyn_note

    return TranslatedQuery(
        source_text=original,
        sql=compiled,
        parameters=params_list,
        referenced_tables=referenced,
        virtual_tables=vtypes,
        note=note,
        is_dynamic=is_dynamic,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════


def translate_1c_query(
    text: str,
    resolver: Callable[[str, str], str | None] | None = None,
    dialect: str = "postgresql",
) -> TranslatedQuery:
    """Translate a single 1C query to SQL.

    Args:
        text: Raw 1C query text (e.g. ``"ВЫБРАТЬ ... ИЗ ..."``).
        resolver: Optional ``(obj_type, obj_name) -> str`` for table name mapping.
        dialect: Target SQL dialect — ``"postgresql"`` (default) or ``"mssql"``.

    Returns:
        TranslatedQuery with .sql compiled for the target dialect.
    """
    return _build_sql(text, resolver=resolver, dialect=dialect)


def extract_queries_from_bsl(
    bsl_text: str,
    resolver: Callable[[str, str], str | None] | None = None,
    dialect: str = "postgresql",
) -> BslQueryResult:
    """Extract and translate all 1C queries from a BSL module text.

    Args:
        bsl_text: Raw BSL source code.
        resolver: Optional callable ``(obj_type, obj_name) -> physical_table_name``.
        dialect: Target SQL dialect — ``"postgresql"`` (default) or ``"mssql"``.

    Returns:
        BslQueryResult with all found queries.
    """
    raw_texts = extract_query_texts(bsl_text)
    if not raw_texts:
        return BslQueryResult(count=0)

    translated: list[TranslatedQuery] = []
    for text in raw_texts:
        tq = translate_1c_query(text, resolver, dialect=dialect)
        translated.append(tq)

    return BslQueryResult(count=len(translated), queries=translated)
