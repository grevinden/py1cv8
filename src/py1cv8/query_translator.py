"""Трансляция языка запросов 1С в SQL
через SQLAlchemy expressions.

Модуль парсит блоки ``Запрос.Текст = "..."``
в BSL-коде, извлекает текст запроса 1С,
заменяет русские ключевые слова на английские,
разрешает ссылки на объекты метаданных
(Справочники, Документы, регистры и т.д.)
в физические имена таблиц БД,
обрабатывает 1С-специфичные конструкции
(виртуальные таблицы, дата-временные функции,
оператор ССЫЛКА, параметры &Имя)
и компилирует результат
в целевой SQL-диалект
(PostgreSQL или MSSQL).

Ключевые возможности:
  - Извлечение запросов из BSL-кода.
  - Подстановка физических имён таблиц
    через внешний resolver.
  - Трансляция 1С-функций даты-времени
    (ГОД, МЕСЯЦ, ДЕНЬ, ЧАС, МИНУТА,
    СЕКУНДА, НАЧАЛОПЕРИОДА,
    ДОБАВИТЬКДАТЕ, РАЗНОСТЬДАТ,
    ДАТАВРЕМЯ).
  - Обработка виртуальных таблиц
    (СрезПоследних, Остатки,
    Обороты, ОстаткиИОбороты,
    ДвиженияССубконто, Движения,
    Кт, Дт, Субконто).
  - Трансляция ключевых слов 1С
    (ВЫБРАТЬ, ИЗ, ГДЕ,
    СОЕДИНЕНИЕ и др.) в SQL.
  - Обработка параметров запроса
    (замена &Имя на :Имя).
  - Обработка ВЫБРАТЬ ПЕРВЫЕ N
    (LIMIT для PG,
    SELECT TOP N для MSSQL).

Пост-процессинг для MSSQL заменяет
PostgreSQL-конструкции
(EXTRACT, DATE_TRUNC, INTERVAL,
DATE_PART, MAKE_DATE,
MAKE_TIMESTAMP, TRUE/FALSE)
на MSSQL-аналоги.

Зависит от внешнего коллера-резолвера
для маппинга имён таблиц
(``TableNameResolver``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql import expression

from py1cv8.protocols import TableNameResolver

# ═══════════════════════════════════════════════════════════════════════════════
# 1C → SQLAlchemy custom function elements with @compiles
# ═══════════════════════════════════════════════════════════════════════════════

# All function-element classes are private and follow 1C naming conventions


class _Year(expression.FunctionElement):
    """SQLAlchemy FunctionElement для функции 1С ГОД().

    Извлекает год из даты/времени. Компилируется в EXTRACT(YEAR FROM expr)
    для PostgreSQL и YEAR(expr) для MSSQL.

    Type:
        sa.Integer() — возвращает целочисленный год.

    Пример использования в 1С:
        ГОД(Дата) → EXTRACT(YEAR FROM datetime_col)
    """

    type = sa.Integer()


@compiles(_Year)
def _compile_year_pg(element, compiler, **kw):
    """Компиляция _Year для PostgreSQL (и других диалектов по умолчанию).

    Генерирует EXTRACT(YEAR FROM expr), где expr — скомпилированное
    выражение-аргумент, переданное в функцию ГОД().

    Args:
        element: Экземпляр _Year, содержащий clause-список с одним аргументом.
        compiler: Экземпляр SQLAlchemy-компилятора для целевого диалекта.
        **kw: Дополнительные ключевые аргументы компилятора.

    Returns:
        str: SQL-фрагмент "EXTRACT(YEAR FROM ...)".
    """
    return f"EXTRACT(YEAR FROM {compiler.process(element.clauses, **kw)})"


@compiles(_Year, "mssql")
def _compile_year_mssql(element, compiler, **kw):
    """Компиляция _Year для MSSQL.

    Генерирует YEAR(expr) — встроенную функцию SQL Server,
    эквивалентную EXTRACT(YEAR FROM expr) в PostgreSQL.

    Args:
        element: Экземпляр _Year, содержащий clause-список с одним аргументом.
        compiler: Экземпляр SQLAlchemy-компилятора для диалекта mssql.
        **kw: Дополнительные ключевые аргументы компилятора.

    Returns:
        str: SQL-фрагмент "YEAR(...)".
    """
    return f"YEAR({compiler.process(element.clauses, **kw)})"


class _Month(expression.FunctionElement):
    """SQLAlchemy FunctionElement для функции 1С МЕСЯЦ().

    Извлекает номер месяца (1-12) из даты/времени. Компилируется в
    EXTRACT(MONTH FROM expr) для PostgreSQL и MONTH(expr) для MSSQL.

    Type:
        sa.Integer() — возвращает целочисленный номер месяца.

    Пример использования в 1С:
        МЕСЯЦ(Дата) → EXTRACT(MONTH FROM datetime_col)
    """

    type = sa.Integer()


@compiles(_Month)
def _compile_month_pg(element, compiler, **kw):
    """Компиляция _Month для PostgreSQL (и других диалектов по умолчанию).

    Генерирует EXTRACT(MONTH FROM expr), аналогично YEAR/MONTH/DAY.

    Args:
        element: Экземпляр _Month, содержащий clause-список с одним аргументом.
        compiler: Экземпляр SQLAlchemy-компилятора для целевого диалекта.
        **kw: Дополнительные ключевые аргументы компилятора.

    Returns:
        str: SQL-фрагмент "EXTRACT(MONTH FROM ...)".
    """
    return f"EXTRACT(MONTH FROM {compiler.process(element.clauses, **kw)})"


@compiles(_Month, "mssql")
def _compile_month_mssql(element, compiler, **kw):
    """Компиляция _Month для MSSQL.

    Генерирует MONTH(expr) — встроенную функцию SQL Server.

    Args:
        element: Экземпляр _Month, содержащий clause-список с одним аргументом.
        compiler: Экземпляр SQLAlchemy-компилятора для диалекта mssql.
        **kw: Дополнительные ключевые аргументы компилятора.

    Returns:
        str: SQL-фрагмент "MONTH(...)".
    """
    return f"MONTH({compiler.process(element.clauses, **kw)})"


class _Day(expression.FunctionElement):
    """SQLAlchemy FunctionElement для функции 1С ДЕНЬ().

    Извлекает номер дня в месяце (1-31) из даты/времени. Компилируется в
    EXTRACT(DAY FROM expr) для PostgreSQL и DAY(expr) для MSSQL.

    Type:
        sa.Integer() — возвращает целочисленный день месяца.

    Пример использования в 1С:
        ДЕНЬ(Дата) → EXTRACT(DAY FROM datetime_col)
    """

    type = sa.Integer()


@compiles(_Day)
def _compile_day_pg(element, compiler, **kw):
    """Компиляция _Day для PostgreSQL (и других диалектов по умолчанию).

    Генерирует EXTRACT(DAY FROM expr), извлекая день месяца из даты.

    Args:
        element: Экземпляр _Day, содержащий clause-список с одним аргументом.
        compiler: Экземпляр SQLAlchemy-компилятора для целевого диалекта.
        **kw: Дополнительные ключевые аргументы компилятора.

    Returns:
        str: SQL-фрагмент "EXTRACT(DAY FROM ...)".
    """
    return f"EXTRACT(DAY FROM {compiler.process(element.clauses, **kw)})"


@compiles(_Day, "mssql")
def _compile_day_mssql(element, compiler, **kw):
    """Компиляция _Day для MSSQL.

    Генерирует DAY(expr) — встроенную функцию SQL Server.

    Args:
        element: Экземпляр _Day, содержащий clause-список с одним аргументом.
        compiler: Экземпляр SQLAlchemy-компилятора для диалекта mssql.
        **kw: Дополнительные ключевые аргументы компилятора.

    Returns:
        str: SQL-фрагмент "DAY(...)".
    """
    return f"DAY({compiler.process(element.clauses, **kw)})"


class _Hour(expression.FunctionElement):
    """SQLAlchemy FunctionElement для функции 1С ЧАС().

    Извлекает часы (0-23) из даты/времени. Компилируется в
    EXTRACT(HOUR FROM expr) для PostgreSQL и DATEPART(hour, expr) для MSSQL.

    Type:
        sa.Integer() — возвращает целочисленный час.

    Пример использования в 1С:
        ЧАС(Время) → EXTRACT(HOUR FROM datetime_col)
    """

    type = sa.Integer()


@compiles(_Hour)
def _compile_hour_pg(element, compiler, **kw):
    """Компиляция _Hour для PostgreSQL (и других диалектов по умолчанию).

    Генерирует EXTRACT(HOUR FROM expr), извлекая часы из временной метки.

    Args:
        element: Экземпляр _Hour, содержащий clause-список с одним аргументом.
        compiler: Экземпляр SQLAlchemy-компилятора для целевого диалекта.
        **kw: Дополнительные ключевые аргументы компилятора.

    Returns:
        str: SQL-фрагмент "EXTRACT(HOUR FROM ...)".
    """
    return f"EXTRACT(HOUR FROM {compiler.process(element.clauses, **kw)})"


@compiles(_Hour, "mssql")
def _compile_hour_mssql(element, compiler, **kw):
    """Компиляция _Hour для MSSQL.

    Генерирует DATEPART(hour, expr) — встроенную функцию SQL Server.

    Args:
        element: Экземпляр _Hour, содержащий clause-список с одним аргументом.
        compiler: Экземпляр SQLAlchemy-компилятора для диалекта mssql.
        **kw: Дополнительные ключевые аргументы компилятора.

    Returns:
        str: SQL-фрагмент "DATEPART(hour, ...)".
    """


class _Minute(expression.FunctionElement):
    """SQLAlchemy FunctionElement для функции 1С МИНУТА().

    Извлекает минуты (0-59) из даты/времени. Компилируется в
    EXTRACT(MINUTE FROM expr) для PostgreSQL и DATEPART(minute, expr) для MSSQL.

    Type:
        sa.Integer() — возвращает целочисленные минуты.

    Пример использования в 1С:
        МИНУТА(Время) → EXTRACT(MINUTE FROM datetime_col)
    """

    type = sa.Integer()


@compiles(_Minute)
def _compile_minute_pg(element, compiler, **kw):
    """Компиляция _Minute для PostgreSQL (и других диалектов по умолчанию).

    Генерирует EXTRACT(MINUTE FROM expr), извлекая минуты из временной метки.

    Args:
        element: Экземпляр _Minute, содержащий clause-список с одним аргументом.
        compiler: Экземпляр SQLAlchemy-компилятора для целевого диалекта.
        **kw: Дополнительные ключевые аргументы компилятора.

    Returns:
        str: SQL-фрагмент "EXTRACT(MINUTE FROM ...)".
    """
    return f"EXTRACT(MINUTE FROM {compiler.process(element.clauses, **kw)})"


@compiles(_Minute, "mssql")
def _compile_minute_mssql(element, compiler, **kw):
    """Компиляция _Minute для MSSQL.

    Генерирует DATEPART(minute, expr) — встроенную функцию SQL Server.

    Args:
        element: Экземпляр _Minute, содержащий clause-список с одним аргументом.
        compiler: Экземпляр SQLAlchemy-компилятора для диалекта mssql.
        **kw: Дополнительные ключевые аргументы компилятора.

    Returns:
        str: SQL-фрагмент "DATEPART(minute, ...)".
    """
    return f"DATEPART(minute, {compiler.process(element.clauses, **kw)})"


class _Second(expression.FunctionElement):
    """SQLAlchemy FunctionElement для функции 1С СЕКУНДА().

    Извлекает секунды (0-59) из даты/времени. Компилируется в
    EXTRACT(SECOND FROM expr) для PostgreSQL и DATEPART(second, expr) для MSSQL.

    Type:
        sa.Integer() — возвращает целочисленные секунды.

    Пример использования в 1С:
        СЕКУНДА(Время) → EXTRACT(SECOND FROM datetime_col)
    """

    type = sa.Integer()


@compiles(_Second)
def _compile_second_pg(element, compiler, **kw):
    """Компиляция _Second для PostgreSQL (и других диалектов по умолчанию).

    Генерирует EXTRACT(SECOND FROM expr), извлекая секунды из временной метки.

    Args:
        element: Экземпляр _Second, содержащий clause-список с одним аргументом.
        compiler: Экземпляр SQLAlchemy-компилятора для целевого диалекта.
        **kw: Дополнительные ключевые аргументы компилятора.

    Returns:
        str: SQL-фрагмент "EXTRACT(SECOND FROM ...)".
    """
    return f"EXTRACT(SECOND FROM {compiler.process(element.clauses, **kw)})"


@compiles(_Second, "mssql")
def _compile_second_mssql(element, compiler, **kw):
    """Компиляция _Second для MSSQL.

    Генерирует DATEPART(second, expr) — встроенную функцию SQL Server.

    Args:
        element: Экземпляр _Second, содержащий clause-список с одним аргументом.
        compiler: Экземпляр SQLAlchemy-компилятора для диалекта mssql.
        **kw: Дополнительные ключевые аргументы компилятора.

    Returns:
        str: SQL-фрагмент "DATEPART(second, ...)".
    """
    return f"DATEPART(second, {compiler.process(element.clauses, **kw)})"


class _DateTrunc(expression.FunctionElement):
    """SQLAlchemy FunctionElement для функции 1С НАЧАЛОПЕРИОДА().

    Усекает дату/время до начала указанного периода (год, квартал, месяц,
    неделя, день, час, минута, секунда). Компилируется в
    DATE_TRUNC(period, expr) для PostgreSQL и DATETRUNC(period, expr) для MSSQL.

    Type:
        sa.DateTime() — возвращает дату/время, усечённую до начала периода.

    Пример использования в 1С:
        НАЧАЛОПЕРИОДА(Дата, "МЕСЯЦ") → DATE_TRUNC('month', date_col)
    """

    type = sa.DateTime()


@compiles(_DateTrunc)
def _compile_date_trunc_pg(element, compiler, **kw):
    """Компиляция _DateTrunc для PostgreSQL (и других диалектов по умолчанию).

    Генерирует DATE_TRUNC(period, expr), где period — строковая константа
    ('year', 'month', 'day', и т.д.), а expr — усекаемое выражение.

    Args:
        element: Экземпляр _DateTrunc, содержащий два clause-аргумента:
            period (строка) и arg (выражение даты/времени).
        compiler: Экземпляр SQLAlchemy-компилятора для целевого диалекта.
        **kw: Дополнительные ключевые аргументы компилятора.

    Returns:
        str: SQL-фрагмент "DATE_TRUNC(period, expr)".
    """
    period, arg = list(element.clauses)
    return f"DATE_TRUNC({compiler.process(period, **kw)}, {compiler.process(arg, **kw)})"


@compiles(_DateTrunc, "mssql")
def _compile_date_trunc_mssql(element, compiler, **kw):
    """Компиляция _DateTrunc для MSSQL.

    Генерирует DATETRUNC(period, expr) — функцию, доступную в SQL Server
    начиная с 2022 года. Эквивалентна PostgreSQL DATE_TRUNC.

    Args:
        element: Экземпляр _DateTrunc, содержащий два clause-аргумента:
            period (строка) и arg (выражение даты/времени).
        compiler: Экземпляр SQLAlchemy-компилятора для диалекта mssql.
        **kw: Дополнительные ключевые аргументы компилятора.

    Returns:
        str: SQL-фрагмент "DATETRUNC(period, expr)".
    """
    period, arg = list(element.clauses)
    p = compiler.process(period, **kw).strip("'")
    return f"DATETRUNC({p}, {compiler.process(arg, **kw)})"


class _DateAdd(expression.FunctionElement):
    """SQLAlchemy FunctionElement для функции 1С ДОБАВИТЬКДАТЕ().

    Добавляет указанное количество периодов к дате/времени. Компилируется в
    (expr + INTERVAL 'count period') для PostgreSQL и
    DATEADD(period, count, expr) для MSSQL.

    Type:
        sa.DateTime() — возвращает новую дату/время после добавления периода.

    Пример использования в 1С:
        ДОБАВИТЬКДАТЕ(Дата, "МЕСЯЦ", 3) → date_col + INTERVAL '3 month'
    """

    type = sa.DateTime()


@compiles(_DateAdd)
def _compile_date_add_pg(element, compiler, **kw):
    """Компиляция _DateAdd для PostgreSQL (и других диалектов по умолчанию).

    Генерирует (expr + INTERVAL 'count period'), используя нативную
    PostgreSQL-операцию сложения с интервалом.

    Args:
        element: Экземпляр _DateAdd, содержащий три clause-аргумента:
            arg (дата/время), count (количество), period (строка периода).
        compiler: Экземпляр SQLAlchemy-компилятора для целевого диалекта.
        **kw: Дополнительные ключевые аргументы компилятора.

    Returns:
        str: SQL-фрагмент "(expr + INTERVAL 'N period')".
    """
    arg, count, period = list(element.clauses)
    a = compiler.process(arg, **kw)
    c = compiler.process(count, **kw)
    p = compiler.process(period, **kw).strip("'")
    return f"({a} + INTERVAL '{c} {p}')"


@compiles(_DateAdd, "mssql")
def _compile_date_add_mssql(element, compiler, **kw):
    """Компиляция _DateAdd для MSSQL.

    Генерирует DATEADD(period, count, expr) — встроенную функцию SQL Server
    для добавления интервала к дате/времени.

    Args:
        element: Экземпляр _DateAdd, содержащий три clause-аргумента:
            arg (дата/время), count (количество), period (строка периода).
        compiler: Экземпляр SQLAlchemy-компилятора для диалекта mssql.
        **kw: Дополнительные ключевые аргументы компилятора.

    Returns:
        str: SQL-фрагмент "DATEADD(period, count, expr)".
    """
    arg, count, period = list(element.clauses)
    a = compiler.process(arg, **kw)
    c = compiler.process(count, **kw)
    p = compiler.process(period, **kw).strip("'")
    return f"DATEADD({p}, {c}, {a})"


class _DateDiff(expression.FunctionElement):
    """SQLAlchemy FunctionElement для функции 1С РАЗНОСТЬДАТ().

    Вычисляет разницу между двумя датами в указанных единицах (год, месяц,
    день и т.д.). Компилируется в DATE_PART('period', expr2 - expr1) для
    PostgreSQL и DATEDIFF(period, expr1, expr2) для MSSQL.

    Type:
        sa.Integer() — возвращает целочисленную разницу в указанных единицах.

    Пример использования в 1С:
        РАЗНОСТЬДАТ(Дата1, Дата2, "ДЕНЬ") → DATE_PART('day', dt2 - dt1)
    """

    type = sa.Integer()


@compiles(_DateDiff)
def _compile_date_diff_pg(element, compiler, **kw):
    """Компиляция _DateDiff для PostgreSQL (и других диалектов по умолчанию).

    Генерирует DATE_PART('period', expr2 - expr1), используя вычитание
    дат и извлечение компонента интервала через DATE_PART.
    ВАЖНО: порядок аргументов в SQL отличается от 1С:
    в 1С: РАЗНОСТЬДАТ(Нач, Кон, "ДЕНЬ"),
    в PG: DATE_PART('day', кон - нач).

    Args:
        element: Экземпляр _DateDiff, содержащий три clause-аргумента:
            arg1 (начальная дата), arg2 (конечная дата),
            period (строка периода).
        compiler: Экземпляр SQLAlchemy-компилятора для целевого диалекта.
        **kw: Дополнительные ключевые аргументы компилятора.

    Returns:
        str: SQL-фрагмент "DATE_PART('period', expr2 - expr1)".
    """
    arg1, arg2, period = list(element.clauses)
    a1 = compiler.process(arg1, **kw)
    a2 = compiler.process(arg2, **kw)
    p = compiler.process(period, **kw).strip("'")
    return f"DATE_PART('{p}', {a2} - {a1})"


@compiles(_DateDiff, "mssql")
def _compile_date_diff_mssql(element, compiler, **kw):
    """Компиляция _DateDiff для MSSQL.

    Генерирует DATEDIFF(period, expr1, expr2) — встроенную функцию SQL Server.
    В MSSQL порядок аргументов такой же, как в 1С: начало, конец.

    Args:
        element: Экземпляр _DateDiff, содержащий три clause-аргумента:
            arg1 (начальная дата), arg2 (конечная дата),
            period (строка периода).
        compiler: Экземпляр SQLAlchemy-компилятора для диалекта mssql.
        **kw: Дополнительные ключевые аргументы компилятора.

    Returns:
        str: SQL-фрагмент "DATEDIFF(period, expr1, expr2)".
    """
    arg1, arg2, period = list(element.clauses)
    a1 = compiler.process(arg1, **kw)
    a2 = compiler.process(arg2, **kw)
    p = compiler.process(period, **kw).strip("'")
    return f"DATEDIFF({p}, {a1}, {a2})"


class _MakeDate(expression.FunctionElement):
    """SQLAlchemy FunctionElement для функции 1С ДАТАВРЕМЯ() (только дата).

    Создаёт дату из компонентов (год, месяц, день). Используется, когда
    в функцию ДАТАВРЕМЯ() передано 3 или менее аргументов.
    Компилируется в MAKE_DATE(year, month, day) для PostgreSQL и
    DATEFROMPARTS(year, month, day) для MSSQL.

    Type:
        sa.Date() — возвращает значение типа DATE.

    Пример использования в 1С:
        ДАТАВРЕМЯ(2024, 1, 15) → MAKE_DATE(2024, 1, 15)
    """

    type = sa.Date()


@compiles(_MakeDate)
def _compile_make_date_pg(element, compiler, **kw):
    """Компиляция _MakeDate для PostgreSQL (и других диалектов по умолчанию).

    Генерирует MAKE_DATE(year, month, day), собирая дату из компонентов.

    Args:
        element: Экземпляр _MakeDate, содержащий clause-список
            с 2-3 аргументами (год, месяц, [день]).
        compiler: Экземпляр SQLAlchemy-компилятора для целевого диалекта.
        **kw: Дополнительные ключевые аргументы компилятора.

    Returns:
        str: SQL-фрагмент "MAKE_DATE(год, месяц, день)".
    """
    args = [compiler.process(c, **kw) for c in element.clauses]
    return f"MAKE_DATE({', '.join(args)})"


@compiles(_MakeDate, "mssql")
def _compile_make_date_mssql(element, compiler, **kw):
    """Компиляция _MakeDate для MSSQL.

    Генерирует DATEFROMPARTS(year, month, day) — встроенную функцию SQL Server.
    Требует ровно 3 аргумента.

    Args:
        element: Экземпляр _MakeDate, содержащий clause-список
            с 3 аргументами (год, месяц, день).
        compiler: Экземпляр SQLAlchemy-компилятора для диалекта mssql.
        **kw: Дополнительные ключевые аргументы компилятора.

    Returns:
        str: SQL-фрагмент "DATEFROMPARTS(год, месяц, день)".
    """
    args = [compiler.process(c, **kw) for c in element.clauses]
    return f"DATEFROMPARTS({', '.join(args)})"


class _MakeTimestamp(expression.FunctionElement):
    """SQLAlchemy FunctionElement для функции 1С ДАТАВРЕМЯ() (дата+время).

    Создаёт дату-время из компонентов (год, месяц, день, час, минута, секунда).
    Используется, когда в функцию ДАТАВРЕМЯ() передано 4-6 аргументов.
    Компилируется в MAKE_TIMESTAMP(...) для PostgreSQL и
    DATETIMEFROMPARTS(...) для MSSQL.

    Type:
        sa.DateTime() — возвращает значение типа TIMESTAMP.

    Пример использования в 1С:
        ДАТАВРЕМЯ(2024, 1, 15, 10, 30, 0) → MAKE_TIMESTAMP(2024, 1, 15, 10, 30, 0)
    """

    type = sa.DateTime()


@compiles(_MakeTimestamp)
def _compile_make_ts_pg(element, compiler, **kw):
    """Компиляция _MakeTimestamp для PostgreSQL (и других диалектов по умолчанию).

    Генерирует MAKE_TIMESTAMP(year, month, day, hour, minute, second),
    собирая временную метку из компонентов.

    Args:
        element: Экземпляр _MakeTimestamp, содержащий clause-список
            с 4-6 аргументами.
        compiler: Экземпляр SQLAlchemy-компилятора для целевого диалекта.
        **kw: Дополнительные ключевые аргументы компилятора.

    Returns:
        str: SQL-фрагмент "MAKE_TIMESTAMP(год, месяц, день, час, мин, сек)".
    """
    args = [compiler.process(c, **kw) for c in element.clauses]
    return f"MAKE_TIMESTAMP({', '.join(args)})"


@compiles(_MakeTimestamp, "mssql")
def _compile_make_ts_mssql(element, compiler, **kw):
    """Компиляция _MakeTimestamp для MSSQL.

    Генерирует DATETIMEFROMPARTS(year, month, day, hour, minute, second,
    milliseconds) — встроенную функцию SQL Server. ВАЖНО: DATETIMEFROMPARTS
    ожидает 8 аргументов (добавляются нулевые миллисекунды при необходимости).

    Args:
        element: Экземпляр _MakeTimestamp, содержащий clause-список
            с 6 аргументами.
        compiler: Экземпляр SQLAlchemy-компилятора для диалекта mssql.
        **kw: Дополнительные ключевые аргументы компилятора.

    Returns:
        str: SQL-фрагмент "DATETIMEFROMPARTS(год, месяц, день, час, мин, сек)".
    """
    args = [compiler.process(c, **kw) for c in element.clauses]
    return f"DATETIMEFROMPARTS({', '.join(args)})"


_PERIOD_RU_TO_EN: dict[str, str] = {
    "СЕКУНДА": "second",
    "МИНУТА": "minute",
    "ЧАС": "hour",
    "ДЕНЬ": "day",
    "НЕДЕЛЯ": "week",
    "МЕСЯЦ": "month",
    "КВАРТАЛ": "quarter",
    "ГОД": "year",
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
    """Результат трансляции одного запроса 1С в SQL.

    Содержит исходный текст запроса на языке запросов 1С,
    скомпилированный SQL для целевого диалекта, список параметров
    запроса (заменённые &Имя → :Имя), информацию о ссылках на
    таблицы метаданных, использованные виртуальные таблицы,
    а также служебные заметки (например, о динамическом построении).

    Attributes:
        source_text: Исходный текст запроса 1С без изменений.
        sql: Скомпилированный SQL-запрос для целевого диалекта
            (PostgreSQL или MSSQL).
        parameters: Список имён параметров запроса, найденных
            в тексте (без префиксов & или :).
        referenced_tables: Список словарей с информацией о ссылках
            на объекты метаданных: name_1c (полное имя в 1С),
            obj_type (тип объекта), obj_name (имя объекта),
            physical_table (физическое имя таблицы, если был resolver).
        virtual_tables: Список использованных виртуальных таблиц
            (СрезПоследних, Остатки, Обороты и т.д.).
        note: Текстовое примечание с пояснениями: динамический
            запрос, конкатенация строк, виртуальные таблицы.
        is_dynamic: Флаг, указывающий, что имя таблицы
            формируется динамически (через ПолноеИмя() или
            конкатенацию строк).
    """

    source_text: str
    sql: str
    parameters: list[str] = field(default_factory=list)
    referenced_tables: list[dict] = field(default_factory=list)
    virtual_tables: list[str] = field(default_factory=list)
    note: str = ""
    is_dynamic: bool = False


@dataclass
class BslQueryResult:
    """Результат извлечения и трансляции всех запросов из BSL-модуля.

    Содержит общее количество найденных запросов и список
    результатов трансляции каждого из них.

    Attributes:
        count: Общее количество найденных запросов в BSL-тексте.
            Может не совпадать с len(queries), если некоторые
            запросы пусты или не удалось распарсить.
        queries: Список объектов TranslatedQuery с результатами
            трансляции каждого найденного запроса.
    """

    count: int
    queries: list[TranslatedQuery] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# BSL extraction
# ═══════════════════════════════════════════════════════════════════════════════


def extract_query_texts(bsl_text: str) -> list[str]:
    """Извлечение сырых текстов запросов 1С из BSL-кода.

    Парсит блоки ``Запрос.Текст = "..."`` в исходном коде на
    встроенном языке 1С (BSL), извлекая содержимое строковых
    литералов. Поддерживает как двойные ("..."), так и одинарные
    ('...') кавычки.

    Функция обрабатывает многострочные запросы с символом |
    в начале продолжения строки (стандартный 1С-синтаксис),
    удаляет лишние пробелы и нормализует переводы строк.

    Если после закрывающего блока ``Запрос.Текст = "..."``
    следует оператор + (конкатенация строк), запрос помечается
    префиксом __CONCAT__ как динамически собираемый.

    Args:
        bsl_text: Исходный текст BSL-модуля для анализа.

    Returns:
        list[str]: Список извлечённых текстов запросов 1С.
            Каждый элемент — это очищенный текст запроса
            (без кавычек, без символов |, с нормализованными
            переводами строк). Для динамических запросов
            добавляется префикс __CONCAT__.
            Пустой список, если ни одного запроса не найдено.
    """
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
    """Нормализация пробельных символов в тексте запроса.

    Заменяет любые последовательности пробельных символов (пробелы,
    табуляции, переводы строк) на одиночный пробел и удаляет
    ведущие/замыкающие пробелы.

    Это необходимо для корректной работы регулярных выражений
    на следующих этапах трансляции, чтобы разрозненные пробелы
    не мешали поиску ключевых слов и конструкций.

    Args:
        text: Исходный текст запроса с произвольным форматированием.

    Returns:
        str: Нормализованный текст с одиночными пробелами между
            словами, без ведущих и замыкающих пробелов.
    """
    return re.sub(r"\s+", " ", text).strip()


def _split_args(args: str) -> list[str]:
    """Разделение строки с аргументами функции по запятым.

    Учитывает вложенность скобок, квадратных и фигурных скобок,
    чтобы не разрывать вложенные выражения. Используется для
    парсинга аргументов 1С-функций даты-времени, которые могут
    содержать вложенные вызовы.

    Алгоритм проходит по строке символ за символом, отслеживая
    текущую глубину вложенности через стек. Запятая считается
    разделителем только на нулевом уровне вложенности.

    Args:
        args: Строка с аргументами функции, разделёнными запятыми.
            Например: "Дата1, Дата2, \"ДЕНЬ\"".

    Returns:
        list[str]: Список отдельных аргументов, очищенных от
            ведущих и замыкающих пробелов. Если строка пуста
            или содержит только один аргумент, возвращается
            список с одним элементом.

    Example:
        >>> _split_args('a, b(b, c), d')
        ['a', 'b(b, c)', 'd']
    """
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
    """Пост-обработка SQL для трансляции в диалект MSSQL.

    Заменяет PostgreSQL-специфичные конструкции на их MSSQL-аналоги.
    Вызывается только когда целевой диалект указан как "mssql".

    Выполняет последовательные замены:
        1. EXTRACT(YEAR|MONTH|DAY FROM x) → YEAR(x)|MONTH(x)|DAY(x)
        2. EXTRACT(HOUR|MINUTE|SECOND FROM x) → DATEPART(part, x)
        3. DATE_TRUNC('period', expr) → DATETRUNC(period, expr)
        4. (expr + INTERVAL 'N period') → DATEADD(period, N, expr)
        5. DATE_PART('period', expr2 - expr1) → DATEDIFF(period, expr1, expr2)
        6. MAKE_DATE(a, b, c) → DATEFROMPARTS(a, b, c)
        7. MAKE_TIMESTAMP(a, b, ...) → DATETIMEFROMPARTS(a, b, ...)
        8. TRUE → 1, FALSE → 0

    Замены выполняются через регулярные выражения с флагом
    re.IGNORECASE для устойчивости к разному регистру.

    Args:
        sql: SQL-запрос, скомпилированный для PostgreSQL,
            с PostgreSQL-специфичными конструкциями.

    Returns:
        str: SQL-запрос с конструкциями, совместимыми с MSSQL.
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
    resolver: TableNameResolver | None = None,
    dialect: str = "postgresql",
) -> TranslatedQuery:
    """Трансляция запроса 1С в SQL для указанного диалекта.

    Основная функция трансляции, выполняющая полный конвейер
    преобразований от текста запроса на языке запросов 1С до
    скомпилированного SQL-выражения для целевого диалекта.

    Конвейер трансляции включает следующие этапы:
        1. Обработка префиксов __DYNAMIC__ и __CONCAT__,
           указывающих на динамическое формирование запроса.
        2. Нормализация пробелов через _normalize().
        3. Сбор информации о ссылках на таблицы метаданных
           (Справочник.Х, Документ.У и т.д.) через resolver.
        4. Замена ссылок на таблицы их физическими именами
           через _replace_table().
        5. Удаление вызовов виртуальных таблиц (СрезПоследних,
           Остатки, Обороты и т.д.) через _strip_vt().
        6. Замена оператора ССЫЛКА → IS OF.
        7. Замена параметров &Имя → :Имя через _param_repl().
        8. Обработка ВЫБРАТЬ ПЕРВЫЕ N → LIMIT/TOP N.
        9. Замена русских ключевых слов на английские SQL.
        10. Переименование 1С-функций (ЕСТЬNULL → COALESCE и др.).
        11. Трансляция дата-временных функций через _replace_date_func().
        12. Применение LIMIT/TOP N в зависимости от диалекта.
        13. MSSQL-специфичная пост-обработка, если dialect == "mssql".
        14. Формирование заметок о виртуальных таблицах.

    Args:
        text: Текст запроса на языке запросов 1С.
        resolver: Опциональный коллер-резолвер для маппинга
            типов объектов 1С в физические имена таблиц БД.
            Сигнатура: (obj_type: str, obj_name: str) -> str | None.
        dialect: Целевой диалект SQL: "postgresql" (по умолчанию)
            или "mssql".

    Returns:
        TranslatedQuery: Структура с исходным текстом, скомпилированным
            SQL, списком параметров, ссылками на таблицы,
            виртуальными таблицами и заметками.
    """
    original = text
    is_dynamic = False
    note = ""
    params_list: list[str] = []
    referenced: list[dict] = []
    vtypes: list[str] = []

    if text.startswith("__DYNAMIC__"):
        is_dynamic = True
        text = text[len("__DYNAMIC__") :].strip()
        note = "[dynamic] table name built at runtime via ПолноеИмя()"
    elif text.startswith("__CONCAT__"):
        text = text[len("__CONCAT__") :].strip()
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
            referenced.append(
                {
                    "name_1c": f"{prefix}.{obj_name}",
                    "obj_type": obj_type,
                    "obj_name": obj_name,
                    "physical_table": table,
                }
            )
        else:
            referenced.append(
                {
                    "name_1c": f"{prefix}.{obj_name}",
                    "obj_type": obj_type,
                    "obj_name": obj_name,
                }
            )

    def _replace_table(m: re.Match) -> str:
        """Замена ссылки на объект метаданных физическим именем таблицы.

        Внутренняя функция, используемая как callback для re.sub().
        Получает совпадение регулярного выражения _RE_TABLE_REF
        и заменяет его на физическое имя таблицы через resolver,
        либо на сгенерированное имя вида "{type}_{name}", если
        resolver не предоставлен или не смог разрешить имя.

        Args:
            m: Объект Match от _RE_TABLE_REF с группами:
                "type" — русское название типа (Справочник, Документ...),
                "name" — имя объекта метаданных.

        Returns:
            str: Физическое имя таблицы (например, "_Reference53")
                или сгенерированное "Справочник_Номенклатура".
        """
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
        """Удаление вызова виртуальной таблицы из текста запроса.

        Внутренняя функция, используемая как callback для re.sub().
        Удаляет из текста запроса конструкцию виртуальной таблицы
        (например, ".СрезПоследних(...)") и запоминает её тип
        в списке vtypes для последующего формирования заметок.

        Виртуальные таблицы не имеют прямых аналогов в SQL, поэтому
        их вызовы удаляются из текста, а в заметки к запросу
        добавляется описание необходимой пост-обработки.

        Args:
            m: Объект Match от _RE_VIRTUAL_TABLE с группой "vt" —
                название виртуальной таблицы (СрезПоследних,
                Остатки, Обороты, ОстаткиИОбороты и т.д.).

        Returns:
            str: Пустая строка (вызов виртуальной таблицы удаляется).
        """
        vt = m.group("vt")
        if vt not in vtypes:
            vtypes.append(vt)
        return ""

    text = _RE_VIRTUAL_TABLE.sub(_strip_vt, text)

    # ── 3. Handle ССЫЛКА → IS OF (only as keyword, not field name) ─────────
    text = _RE_SSYLKA.sub("IS OF", text)

    # ── 4. Parameters: &Param → :Param (SQLAlchemy named bind param) ────────
    def _param_repl(m: re.Match) -> str:
        """Замена параметра запроса формата &Имя на :Имя.

        Внутренняя функция, используемая как callback для re.sub().
        Преобразует 1С-параметры (префикс &) в именованные
        bind-параметры SQLAlchemy (префикс :). Также собирает
        имена параметров в список params_list для последующего
        возврата в TranslatedQuery.

        Args:
            m: Объект Match от _RE_PARAM с группой 1 — имя
                параметра без префикса &.

        Returns:
            str: Имя параметра с префиксом : (например, ":ДатаНач").
        """
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
        text = "ВЫБРАТЬ " + text[top_m.end() :]

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
    date_func_names = "|".join(
        [
            "ГОД",
            "МЕСЯЦ",
            "ДЕНЬ",
            "ЧАС",
            "МИНУТА",
            "СЕКУНДА",
            "НАЧАЛОПЕРИОДА",
            "ДОБАВИТЬКДАТЕ",
            "РАЗНОСТЬДАТ",
            "ДАТАВРЕМЯ",
        ]
    )
    _re_date_func = re.compile(
        rf"(?P<name>{date_func_names})\s*\((?P<args>[^)]*)\)",
        re.IGNORECASE,
    )

    def _replace_date_func(m: re.Match) -> str:
        """Замена 1С-функций даты-времени на SQL-выражения.

        Внутренняя функция, используемая как callback для re.sub().
        Транслирует следующие 1С-функции:

        - ДАТАВРЕМЯ(год, месяц, день[, час, мин, сек]) →
            MAKE_DATE(...) или MAKE_TIMESTAMP(...)
        - ГОД|МЕСЯЦ|ДЕНЬ|ЧАС|МИНУТА|СЕКУНДА(дата) →
            EXTRACT(part FROM дата)
        - НАЧАЛОПЕРИОДА(дата, "период") →
            DATE_TRUNC('period', дата)
        - ДОБАВИТЬКДАТЕ(дата, "период", число) →
            (дата + INTERVAL 'число период')
        - РАЗНОСТЬДАТ(дата1, дата2, "период") →
            DATE_PART('period', дата2 - дата1)

        Русские названия периодов переводятся в английские
        через словарь _PERIOD_RU_TO_EN.

        Args:
            m: Объект Match от _re_date_func с группами:
                "name" — название функции (ГОД, МЕСЯЦ, ДАТАВРЕМЯ...),
                "args" — строка с аргументами внутри скобок.

        Returns:
            str: Скомпилированное SQL-выражение, соответствующее
                1С-функции. Если функция не распознана или
                аргументы некорректны — возвращает исходный
                текст без изменений.
        """
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
                "ГОД": "YEAR",
                "МЕСЯЦ": "MONTH",
                "ДЕНЬ": "DAY",
                "ЧАС": "HOUR",
                "МИНУТА": "MINUTE",
                "СЕКУНДА": "SECOND",
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
            vt_notes.append("СрезПоследних: virtual table = DISTINCT ON + ORDER BY _Period DESC")
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
    resolver: TableNameResolver | None = None,
    dialect: str = "postgresql",
) -> TranslatedQuery:
    """Трансляция одного запроса 1С в SQL для указанного диалекта.

    Публичная функция-обёртка над _build_sql(). Принимает текст запроса
    на языке запросов 1С, опциональный resolver для маппинга имён
    таблиц и целевой диалект SQL.

    Результат включает скомпилированный SQL, список использованных
    параметров, ссылки на таблицы метаданных и информацию о
    виртуальных таблицах.

    Args:
        text: Текст запроса на языке запросов 1С.
            Например: '\"ВЫБРАТЬ * ИЗ Справочник.Номенклатура\"'.
        resolver: Опциональный коллер-резолвер для преобразования
            типов объектов 1С (Reference, Document, ...) и имён
            объектов в физические имена таблиц БД.
            Сигнатура: (obj_type: str, obj_name: str) -> str | None.
        dialect: Целевой диалект SQL. Поддерживаются:
            "postgresql" (по умолчанию) и "mssql".

    Returns:
        TranslatedQuery: Объект с полями:
            - source_text: исходный текст запроса 1С
            - sql: скомпилированный SQL
            - parameters: список имён параметров (&Имя)
            - referenced_tables: информация о ссылках на таблицы
            - virtual_tables: использованные виртуальные таблицы
            - note: примечания (динамический запрос, вирт. таблицы)
            - is_dynamic: флаг динамического формирования

    Пример:
        >>> tq = translate_1c_query('ВЫБРАТЬ * ИЗ Справочник.Номенклатура')
        >>> tq.sql
        'SELECT * FROM _Reference53'
    """
    return _build_sql(text, resolver=resolver, dialect=dialect)


def extract_queries_from_bsl(
    bsl_text: str,
    resolver: TableNameResolver | None = None,
    dialect: str = "postgresql",
) -> BslQueryResult:
    """Извлечение и трансляция всех запросов 1С из BSL-модуля.

    Высокоуровневая функция, которая:
    1. Извлекает все блоки ``Запрос.Текст = "..."`` из BSL-кода
       через extract_query_texts().
    2. Транслирует каждый найденный запрос через translate_1c_query().
    3. Собирает результаты в структуру BslQueryResult.

    Args:
        bsl_text: Исходный текст BSL-модуля (встроенный язык 1С)
            для анализа и извлечения запросов.
        resolver: Опциональный коллер-резолвер для маппинга
            типов объектов 1С в физические имена таблиц БД.
            Сигнатура: (obj_type: str, obj_name: str) -> str | None.
        dialect: Целевой диалект SQL для компиляции запросов:
            "postgresql" (по умолчанию) или "mssql".

    Returns:
        BslQueryResult: Объект с полями:
            - count: количество найденных запросов
            - queries: список объектов TranslatedQuery

    Пример:
        >>> bsl = '\nЗапрос.Текст = "ВЫБРАТЬ * ИЗ Справочник.Номенклатура";'
        >>> result = extract_queries_from_bsl(bsl)
        >>> result.count
        1
    """
    raw_texts = extract_query_texts(bsl_text)
    if not raw_texts:
        return BslQueryResult(count=0)

    translated: list[TranslatedQuery] = []
    for text in raw_texts:
        tq = translate_1c_query(text, resolver, dialect=dialect)
        translated.append(tq)

    return BslQueryResult(count=len(translated), queries=translated)
