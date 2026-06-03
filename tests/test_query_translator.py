"""Tests for query_translator — 1C query → SQL translation."""

from __future__ import annotations

from py1cv8.query_translator import (
    extract_query_texts,
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
    q = "ВЫБРАТЬ МАКСИМУМ(Цена), МИНИМУМ(Цена), СУММА(Цена), КОЛИЧЕСТВО(*) ИЗ Справочник.Номенклатура"
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
