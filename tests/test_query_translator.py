"""Tests for query_translator — 1C query → SQL translation."""

from __future__ import annotations

from py1cv8.query_translator import (
    BslQueryResult,
    extract_query_texts,
    extract_queries_from_bsl,
    translate_1c_query,
)


def _resolver(obj_type: str, obj_name: str) -> str | None:
    m = {
        ("Document", "Уведомления"): "_Document104",
        ("Reference", "ЗашифрованныеДанные"): "_Reference42",
        ("InfoRg", "ЦеныНоменклатуры"): "_InfoRg432",
    }
    return m.get((obj_type, obj_name))


# ── BSL extraction ──────────────────────────────────────────────────────────


def test_extract_simple_query():
    bsl = 'Запрос.Текст = "ВЫБРАТЬ 1 ИЗ Справочник.Сотрудники ГДЕ Ссылка = &Ссылка";'
    result = extract_query_texts(bsl)
    assert len(result) == 1
    assert "ВЫБРАТЬ 1" in result[0]
    assert "Справочник.Сотрудники" in result[0]


def test_extract_multi_line_query():
    bsl = """Запрос.Текст = "ВЫБРАТЬ ПЕРВЫЕ 1
               |	Уведомления.Ссылка КАК Ссылка
               |ИЗ
               |	Документ.Уведомления КАК Уведомления
               |ГДЕ
               |	НЕ Уведомления.Проведен
               |УПОРЯДОЧИТЬ ПО
               |	Уведомления.Номер";"""
    result = extract_query_texts(bsl)
    assert len(result) == 1
    text = result[0]
    assert "ВЫБРАТЬ ПЕРВЫЕ 1" in text
    assert "Документ.Уведомления" in text
    assert "Уведомления.Ссылка" in text
    # | prefix should be cleaned
    assert "|\t" not in text


def test_extract_comment_skipped():
    bsl = """//Запрос.Текст = ТекстЗапроса;
Запрос.Текст = "ВЫБРАТЬ 1";"""
    result = extract_query_texts(bsl)
    assert len(result) == 1
    assert "ВЫБРАТЬ 1" in result[0]


def test_extract_no_queries():
    assert extract_query_texts("") == []
    assert extract_query_texts("Процедура Тест()\nКонецПроцедуры") == []


def test_extract_concat_detected():
    """Concatenated queries get __CONCAT__ prefix."""
    bsl = 'Запрос.Текст = "ВЫБРАТЬ Т.Ссылка ИЗ " + ОбъектМД.ПолноеИмя() + " КАК Т";'
    result = extract_query_texts(bsl)
    assert len(result) == 1
    assert result[0].startswith("__CONCAT__")


# ── Keyword translation ─────────────────────────────────────────────────────


def test_translate_basic_select():
    q = "ВЫБРАТЬ 1 ИЗ Справочник.Сотрудники ГДЕ Ссылка = &Ссылка"
    r = translate_1c_query(q)
    assert "SELECT 1" in r.sql
    assert "FROM" in r.sql
    assert "WHERE" in r.sql
    assert "Ссылка" in r.sql  # field name preserved, not IS OF
    assert ":Ссылка" in r.sql  # & param → SQLAlchemy named param


def test_translate_select_top():
    q = "ВЫБРАТЬ ПЕРВЫЕ 5 Уведомления.Ссылка ИЗ Документ.Уведомления КАК Уведомления"
    r = translate_1c_query(q)
    assert "SELECT" in r.sql
    assert "LIMIT 5" in r.sql
    assert r.sql.index("LIMIT") > r.sql.index("FROM")


def test_translate_case():
    q = (
        "ВЫБРАТЬ ВЫБОР КОГДА Значение ССЫЛКА Справочник.ЗашифрованныеДанные "
        'ТОГДА "{{ val }}" ИНАЧЕ Значение КОНЕЦ КАК Поле ИЗ Справочник.ЗашифрованныеДанные'
    )
    r = translate_1c_query(q)
    assert "CASE" in r.sql
    assert "WHEN" in r.sql
    assert "THEN" in r.sql
    assert "ELSE" in r.sql
    assert "END" in r.sql
    assert "IS OF" in r.sql


def test_translate_booleans():
    q = "ВЫБРАТЬ ИСТИНА КАК Флаг, ЛОЖЬ КАК НеФлаг, НЕОПРЕДЕЛЕНО КАК Пусто"
    r = translate_1c_query(q)
    assert "TRUE" in r.sql
    assert "FALSE" in r.sql
    assert "NULL" in r.sql


def test_translate_join():
    q = (
        "ВЫБРАТЬ Т.Ссылка ИЗ Документ.Уведомления.Товары КАК Т "
        "ВНУТРЕННЕЕ СОЕДИНЕНИЕ РегистрСведений.ЦеныНоменклатуры.СрезПоследних КАК Ц "
        "ПО Т.Номенклатура = Ц.Номенклатура"
    )
    r = translate_1c_query(q)
    assert "INNER JOIN" in r.sql
    assert "ON" in r.sql


def test_translate_union():
    q = "ВЫБРАТЬ 1 КАК А ОБЪЕДИНИТЬ ВСЕ ВЫБРАТЬ 2 КАК А"
    r = translate_1c_query(q)
    assert "UNION ALL" in r.sql


# ── Virtual tables ──────────────────────────────────────────────────────────


def test_virtual_slice_last():
    q = "ВЫБРАТЬ МАКСИМУМ(Цена) КАК Цена ИЗ РегистрСведений.ЦеныНоменклатуры.СрезПоследних"
    r = translate_1c_query(q)
    assert any("СрезПоследних" in v for v in r.virtual_tables)
    assert "СрезПоследних" in r.note


# ── Functions ────────────────────────────────────────────────────────────────


def test_function_aggregate():
    q = (
        "ВЫБРАТЬ МАКСИМУМ(Цена), МИНИМУМ(Цена), СУММА(Цена),"
        " КОЛИЧЕСТВО(*) ИЗ Справочник.Номенклатура"
    )
    r = translate_1c_query(q)
    assert "MAX(" in r.sql
    assert "MIN(" in r.sql
    assert "SUM(" in r.sql
    assert "COUNT(" in r.sql


def test_function_coalesce():
    q = "ВЫБРАТЬ ЕСТЬNULL(Цена, 0) КАК Цена ИЗ Справочник.Номенклатура"
    r = translate_1c_query(q)
    assert "COALESCE" in r.sql


# ── Resolver ────────────────────────────────────────────────────────────────


def test_resolver_maps_table():
    q = "ВЫБРАТЬ 1 ИЗ Документ.Уведомления"
    r = translate_1c_query(q, _resolver)
    assert "_Document104" in r.sql
    assert len(r.referenced_tables) == 1
    assert r.referenced_tables[0]["physical_table"] == "_Document104"


def test_resolver_handles_unresolved():
    q = "ВЫБРАТЬ 1 ИЗ Справочник.НеизвестныйСправочник"
    r = translate_1c_query(q, _resolver)
    # Unresolved table should keep readable name
    assert "Справочник_НеизвестныйСправочник" in r.sql
    assert r.referenced_tables[0].get("physical_table") is None


# ── Dynamic query detection ──────────────────────────────────────────────────


def test_dynamic_query_detected():
    r = translate_1c_query("__DYNAMIC__ ВЫБРАТЬ Т.Ссылка ИЗ xxx КАК Т")
    assert r.is_dynamic
    assert "dynamic" in r.note


# ── MSSQL dialect ─────────────────────────────────────────────────────────────


def test_mssql_select_top():
    q = "ВЫБРАТЬ ПЕРВЫЕ 5 Уведомления.Ссылка ИЗ Документ.Уведомления КАК Уведомления"
    r = translate_1c_query(q, dialect="mssql")
    assert "SELECT TOP 5" in r.sql
    assert "FROM" in r.sql


def test_mssql_params():
    q = "ВЫБРАТЬ 1 ГДЕ Ссылка = &Ссылка"
    r = translate_1c_query(q, dialect="mssql")
    assert ":Ссылка" in r.sql


def test_mssql_ssylka_preserved():
    q = "ВЫБРАТЬ Ссылка ИЗ Справочник.Сотрудники ГДЕ Ссылка = &Ссылка"
    r = translate_1c_query(q, dialect="mssql")
    assert "Ссылка" in r.sql  # field name preserved
    assert "IS OF" not in r.sql  # only if followed by type name


def test_mssql_function_year():
    q = "ВЫБРАТЬ ГОД(Дата) КАК Год ИЗ Справочник.Документы"
    r = translate_1c_query(q, dialect="mssql")
    assert "YEAR(" in r.sql or "EXTRACT" in r.sql  # MSSQL still uses EXTRACT for now


# ── Parameters ───────────────────────────────────────────────────────────────


def test_parameters_extracted():
    q = "ВЫБРАТЬ 1 ИЗ Справочник.Сотрудники ГДЕ Ссылка = &Ссылка И Номер = &Номер"
    r = translate_1c_query(q)
    assert ":Ссылка" in r.sql
    assert ":Номер" in r.sql
    assert "Ссылка" in r.parameters
    assert "Номер" in r.parameters


# ── Date functions (PG) ─────────────────────────────────────────────────────


def test_date_make_date():
    q = "ВЫБРАТЬ ДАТАВРЕМЯ(2024, 1, 15) КАК Дата"
    r = translate_1c_query(q)
    assert "MAKE_DATE(2024, 1, 15)" in r.sql


def test_date_make_timestamp():
    q = "ВЫБРАТЬ ДАТАВРЕМЯ(2024, 1, 15, 10, 30, 0) КАК Дата"
    r = translate_1c_query(q)
    assert "MAKE_TIMESTAMP(2024, 1, 15, 10, 30, 0)" in r.sql


def test_date_make_date_two_args():
    q = "ВЫБРАТЬ ДАТАВРЕМЯ(2024, 1) КАК Дата"
    r = translate_1c_query(q)
    assert "MAKE_DATE(2024)" in r.sql  # <3 args → only first arg used


def test_date_trunc_month():
    q = "ВЫБРАТЬ НАЧАЛОПЕРИОДА(Дата, МЕСЯЦ) КАК Период ИЗ Документ.Заказ"
    r = translate_1c_query(q)
    assert "DATE_TRUNC('month', Дата)" in r.sql


def test_date_trunc_fallback():
    q = "ВЫБРАТЬ НАЧАЛОПЕРИОДА(Дата) КАК Период ИЗ Документ.Заказ"
    r = translate_1c_query(q)
    assert "НАЧАЛОПЕРИОДА(Дата)" in r.sql


def test_date_add_day():
    q = "ВЫБРАТЬ ДОБАВИТЬКДАТЕ(Дата, ДЕНЬ, 5) КАК НоваяДата ИЗ Документ.Заказ"
    r = translate_1c_query(q)
    assert "INTERVAL '5 day'" in r.sql


def test_date_add_fallback():
    q = "ВЫБРАТЬ ДОБАВИТЬКДАТЕ(Дата, ДЕНЬ) КАК НоваяДата ИЗ Документ.Заказ"
    r = translate_1c_query(q)
    assert "ДОБАВИТЬКДАТЕ(Дата, ДЕНЬ)" in r.sql


def test_date_add_nested():
    """Nested ДАТАВРЕМЯ inside ДОБАВИТЬКДАТЕ triggers _split_args depth >0."""
    q = "ВЫБРАТЬ ДОБАВИТЬКДАТЕ(ДАТАВРЕМЯ(2024, 1, 15), ДЕНЬ, 5) ИЗ Документ.Заказ"
    r = translate_1c_query(q)
    # Nested parens: regex consumes only up to first ),
    # outer ДОБАВИТЬКДАТЕ falls back to original text
    assert "ДОБАВИТЬКДАТЕ" in r.sql


def test_date_diff_day():
    q = "ВЫБРАТЬ РАЗНОСТЬДАТ(Дата1, Дата2, ДЕНЬ) КАК Разница ИЗ Документ.Заказ"
    r = translate_1c_query(q)
    assert "DATE_PART('day', Дата2 - Дата1)" in r.sql


def test_date_diff_fallback():
    q = "ВЫБРАТЬ РАЗНОСТЬДАТ(Дата1, Дата2) КАК Разница ИЗ Документ.Заказ"
    r = translate_1c_query(q)
    assert "РАЗНОСТЬДАТ(Дата1, Дата2)" in r.sql


# ── Date functions (MSSQL) ──────────────────────────────────────────────────


def test_mssql_date_make_date():
    q = "ВЫБРАТЬ ДАТАВРЕМЯ(2024, 1, 15) КАК Дата"
    r = translate_1c_query(q, dialect="mssql")
    assert "DATEFROMPARTS(2024, 1, 15)" in r.sql


def test_mssql_date_make_timestamp():
    q = "ВЫБРАТЬ ДАТАВРЕМЯ(2024, 1, 15, 10, 30, 0) КАК Дата"
    r = translate_1c_query(q, dialect="mssql")
    assert "DATETIMEFROMPARTS(2024, 1, 15, 10, 30, 0)" in r.sql


def test_mssql_date_trunc_month():
    q = "ВЫБРАТЬ НАЧАЛОПЕРИОДА(Дата, МЕСЯЦ) КАК Период ИЗ Документ.Заказ"
    r = translate_1c_query(q, dialect="mssql")
    assert "DATETRUNC(month, Дата)" in r.sql


def test_mssql_date_add_day():
    q = "ВЫБРАТЬ ДОБАВИТЬКДАТЕ(Дата, ДЕНЬ, 5) КАК НоваяДата ИЗ Документ.Заказ"
    r = translate_1c_query(q, dialect="mssql")
    assert "DATEADD(day, 5, Дата)" in r.sql


def test_mssql_date_diff_day():
    q = "ВЫБРАТЬ РАЗНОСТЬДАТ(Дата1, Дата2, ДЕНЬ) КАК Разница ИЗ Документ.Заказ"
    r = translate_1c_query(q, dialect="mssql")
    assert "DATEDIFF(day, Дата1, Дата2)" in r.sql


def test_mssql_hour_minute_second():
    q = "ВЫБРАТЬ ЧАС(Дата), МИНУТА(Дата), СЕКУНДА(Дата) ИЗ Документ.Заказ"
    r = translate_1c_query(q, dialect="mssql")
    assert "DATEPART(HOUR, Дата)" in r.sql
    assert "DATEPART(MINUTE, Дата)" in r.sql
    assert "DATEPART(SECOND, Дата)" in r.sql


def test_mssql_booleans():
    q = "ВЫБРАТЬ ИСТИНА КАК Флаг, ЛОЖЬ КАК НеФлаг"
    r = translate_1c_query(q, dialect="mssql")
    assert "1" in r.sql  # TRUE → 1
    assert "0" in r.sql  # FALSE → 0


# ── Period variant (НЕДЕЛЯ, КВАРТАЛ, ГОД) ──────────────────────────────────


def test_date_period_variants():
    for period, en_p in [("НЕДЕЛЯ", "week"), ("КВАРТАЛ", "quarter"), ("ГОД", "year")]:
        q = f"ВЫБРАТЬ НАЧАЛОПЕРИОДА(Дата, {period}) ИЗ Документ.Заказ"
        r = translate_1c_query(q)
        assert f"DATE_TRUNC('{en_p}', Дата)" in r.sql, f"failed for {period}"


def test_date_add_period_variants():
    for period, en_p in [("НЕДЕЛЯ", "week"), ("КВАРТАЛ", "quarter"), ("ГОД", "year")]:
        q = f"ВЫБРАТЬ ДОБАВИТЬКДАТЕ(Дата, {period}, 1) ИЗ Документ.Заказ"
        r = translate_1c_query(q)
        assert f"INTERVAL '1 {en_p}'" in r.sql, f"failed for {period}"


def test_date_diff_period_variants():
    for period, en_p in [("НЕДЕЛЯ", "week"), ("КВАРТАЛ", "quarter"), ("ГОД", "year")]:
        q = f"ВЫБРАТЬ РАЗНОСТЬДАТ(Дата1, Дата2, {period}) ИЗ Документ.Заказ"
        r = translate_1c_query(q)
        assert f"DATE_PART('{en_p}', Дата2 - Дата1)" in r.sql, f"failed for {period}"


# ── More virtual tables ─────────────────────────────────────────────────────


def test_virtual_balances():
    q = "ВЫБРАТЬ Товар, Количество ИЗ РегистрНакопления.Товары.Остатки(Дата=&Дата)"
    r = translate_1c_query(q)
    assert "Остатки" in r.virtual_tables
    assert "SUM(balance)" in r.note


def test_virtual_turnovers():
    q = "ВЫБРАТЬ Товар, Оборот ИЗ РегистрНакопления.Товары.Обороты(Период=&Период)"
    r = translate_1c_query(q)
    assert "Обороты" in r.virtual_tables
    assert "SUM(turnover)" in r.note


def test_virtual_balances_and_turnovers():
    q = "ВЫБРАТЬ Товар, Количество, Оборот ИЗ РегистрНакопления.Товары.ОстаткиИОбороты"
    r = translate_1c_query(q)
    assert "ОстаткиИОбороты" in r.virtual_tables
    assert "balances + turnovers" in r.note


def test_virtual_subconto():
    q = "ВЫБРАТЬ Субконто1, ДтОборот ИЗ РегистрБухгалтерии.Хозрасчетный.ДвиженияССубконто"
    r = translate_1c_query(q)
    assert "ДвиженияССубконто" in r.virtual_tables
    assert "subconto" in r.note


# ── __CONCAT__ translation ──────────────────────────────────────────────────


def test_concat_translation():
    r = translate_1c_query("__CONCAT__ ВЫБРАТЬ 1 ИЗ Справочник.Сотрудники")
    assert r.is_dynamic
    assert "concat" in r.note


# ── extract_queries_from_bsl ────────────────────────────────────────────────


def test_extract_queries_from_bsl_basic():
    bsl = 'Запрос.Текст = "ВЫБРАТЬ 1 ИЗ Справочник.Сотрудники";'
    result = extract_queries_from_bsl(bsl)
    assert result.count == 1
    assert len(result.queries) == 1
    assert "SELECT 1" in result.queries[0].sql


def test_extract_queries_from_bsl_empty():
    result = extract_queries_from_bsl("")
    assert result.count == 0
    assert result.queries == []


def test_extract_queries_from_bsl_with_resolver():
    bsl = 'Запрос.Текст = "ВЫБРАТЬ 1 ИЗ Документ.Уведомления";'
    result = extract_queries_from_bsl(bsl, _resolver)
    assert result.count == 1
    assert "_Document104" in result.queries[0].sql


def test_extract_queries_from_bsl_mssql():
    bsl = 'Запрос.Текст = "ВЫБРАТЬ ПЕРВЫЕ 5 Ссылка ИЗ Справочник.Сотрудники";'
    result = extract_queries_from_bsl(bsl, dialect="mssql")
    assert result.count == 1
    assert "SELECT TOP 5" in result.queries[0].sql


def test_extract_queries_from_bsl_multiple():
    bsl = (
        'Запрос.Текст = "ВЫБРАТЬ 1";\n'
        'Запрос2.Текст = "ВЫБРАТЬ 2";\n'
    )
    result = extract_queries_from_bsl(bsl)
    assert result.count == 1  # only Запрос.Текст matches
    assert "SELECT 1" in result.queries[0].sql
