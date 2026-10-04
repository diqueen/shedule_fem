"""Parser tests, driven entirely by local fixtures."""
from __future__ import annotations

from datetime import date

import pytest

from app.parser.client import _parse_groups, _parse_months
from app.parser.exceptions import ScheduleStructureError
from app.parser.parser import (
    extract_lesson_type,
    month_name_to_number,
    parse_catalog,
    parse_month_html,
    parse_time_range,
    resolve_year,
    strip_lesson_suffix,
)

REFERENCE = date(2026, 10, 2)


# --------------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------------- #
def test_parse_catalog_education_levels(catalog):
    names = [level.name for level in catalog.education_levels]
    assert names == ["СПО", "Бакалавриат", "Магистратура"]
    assert catalog.education_levels[0].id == "2320"


def test_parse_catalog_specials_and_courses(catalog):
    bachelor = next(lvl for lvl in catalog.education_levels if lvl.name == "Бакалавриат")
    specials = catalog.specialities_for(bachelor.id)
    assert any(s.name == "Экономика" for s in specials)
    economics = next(s for s in specials if s.name == "Экономика")
    courses = [c.number for c in catalog.courses_for(economics.id)]
    assert courses == [1, 2, 3, 4]


def test_parse_catalog_missing_filter_section():
    with pytest.raises(ScheduleStructureError):
        parse_catalog("<html><body>no filters here</body></html>")


# --------------------------------------------------------------------------- #
# JSON endpoints
# --------------------------------------------------------------------------- #
def test_parse_groups_json(groups_json):
    groups = _parse_groups(groups_json)
    assert groups[0].name == "6511,6512"
    assert groups[0].external_id == "6511,6512"


def test_parse_months_json(months_json):
    assert _parse_months(months_json) == ["сентябрь", "октябрь"]


def test_parse_groups_rejects_html():
    with pytest.raises(ScheduleStructureError):
        _parse_groups("<!DOCTYPE html><html></html>")


# --------------------------------------------------------------------------- #
# Month table (real fixtures)
# --------------------------------------------------------------------------- #
def test_parse_october_fixture(october_html):
    result = parse_month_html(october_html, REFERENCE)
    assert result.entries
    assert all(e.schedule_date.year == 2026 for e in result.entries)
    assert all(e.schedule_date.month == 10 for e in result.entries)
    assert result.groups == {"6511,6512"}

    first = result.entries[0]
    assert first.start_time is not None and first.end_time is not None
    assert first.subject
    assert first.subject_raw
    assert first.source_id


def test_parse_november_fixture_year(november_html):
    result = parse_month_html(november_html, REFERENCE)
    assert result.entries
    assert all(e.schedule_date.month == 11 for e in result.entries)
    assert all(e.schedule_date.year == 2026 for e in result.entries)


def test_parse_lesson_types_present(october_html):
    result = parse_month_html(october_html, REFERENCE)
    types = {e.lesson_type for e in result.entries}
    assert "практика" in types
    assert "лабораторная" in types
    assert "лекция" in types


def test_empty_month_table_is_not_an_error():
    html = (
        '<table><caption>октябрь</caption>'
        '<tr class="lesson-line"><td>Дата</td><td id="day5">5 Октября</td></tr>'
        "</table>"
    )
    result = parse_month_html(html, REFERENCE)
    assert result.entries == []


def test_missing_table_raises():
    with pytest.raises(ScheduleStructureError):
        parse_month_html("<div>nothing here</div>", REFERENCE)


def test_empty_html_returns_empty_result():
    result = parse_month_html("", REFERENCE)
    assert result.entries == []


# --------------------------------------------------------------------------- #
# Cell-level edge cases (synthetic)
# --------------------------------------------------------------------------- #
def _table_with_cell(cell: str) -> str:
    return (
        '<table><caption>октябрь</caption>'
        '<tr class="lesson-line"><td>Дата</td><td id="day5">5 Октября</td></tr>'
        f"<tr><td>09:30 - 11:10</td>{cell}</tr>"
        "</table>"
    )


def test_cell_missing_subject_is_skipped():
    cell = (
        '<td data-id="10" data-group="6511" data-day="5" data-time="09:30 - 11:10" '
        'data-month="октябрь"><div class="subject"></div><div class="aud"><b>а.1</b></div>'
        "Иванов И. И.<div class=\"number\">(1)1</div></td>"
    )
    assert parse_month_html(_table_with_cell(cell), REFERENCE).entries == []


def test_cell_missing_aud_gives_none():
    cell = (
        '<td data-id="11" data-group="6511" data-day="5" data-time="09:30 - 11:10" '
        'data-month="октябрь"><div class="subject">Математика (лек)</div>'
        'Иванов И. И.<div class="number">(1)1</div></td>'
    )
    entries = parse_month_html(_table_with_cell(cell), REFERENCE).entries
    assert entries[0].classroom is None
    assert entries[0].teacher == "Иванов И. И."


def test_cell_missing_teacher_gives_none():
    cell = (
        '<td data-id="12" data-group="6511" data-day="5" data-time="09:30 - 11:10" '
        'data-month="октябрь"><div class="subject">Математика (лек)</div>'
        '<div class="aud"><b>а.1</b></div><div class="number">(1)1</div></td>'
    )
    entries = parse_month_html(_table_with_cell(cell), REFERENCE).entries
    assert entries[0].teacher is None
    assert entries[0].classroom == "а.1"


def test_cell_placeholder_teacher_is_none():
    cell = (
        '<td data-id="13" data-group="6511" data-day="5" data-time="09:30 - 11:10" '
        'data-month="октябрь"><div class="subject">Физкультура (пр)</div>'
        '<div class="aud"><b></b></div> . .<div class="number"></div></td>'
    )
    entries = parse_month_html(_table_with_cell(cell), REFERENCE).entries
    assert entries[0].teacher is None
    assert entries[0].classroom is None


def test_cell_multiple_teachers_text_preserved():
    cell = (
        '<td data-id="14" data-group="6511" data-day="5" data-time="09:30 - 11:10" '
        'data-month="октябрь"><div class="subject">Математика (лек)</div>'
        '<div class="aud"><b>а.1</b></div>Иванов И. И., Петров П. П.<div class="number"></div></td>'
    )
    entries = parse_month_html(_table_with_cell(cell), REFERENCE).entries
    assert entries[0].teacher == "Иванов И. И., Петров П. П."


def test_cell_multiple_groups_preserved():
    cell = (
        '<td data-id="15" data-group="6511,6512" data-day="5" data-time="09:30 - 11:10" '
        'data-month="октябрь"><div class="subject">Математика (лек)</div>'
        '<div class="aud"><b>а.1</b></div>Иванов И. И.<div class="number"></div></td>'
    )
    entries = parse_month_html(_table_with_cell(cell), REFERENCE).entries
    assert entries[0].group_id == "6511,6512"


def test_cell_data_not_becomes_note():
    cell = (
        '<td data-id="16" data-group="6511" data-day="5" data-time="09:30 - 11:10" '
        'data-month="октябрь" data-not="Замена"><div class="subject">Математика (лек)</div>'
        '<div class="aud"><b>а.1</b></div>Иванов И. И.<div class="number"></div></td>'
    )
    entries = parse_month_html(_table_with_cell(cell), REFERENCE).entries
    assert entries[0].note == "Замена"


def test_cell_invalid_date_is_skipped():
    cell = (
        '<td data-id="17" data-group="6511" data-day="99" data-time="09:30 - 11:10" '
        'data-month="октябрь"><div class="subject">Математика (лек)</div>'
        '<div class="aud"><b>а.1</b></div>Иванов И. И.<div class="number"></div></td>'
    )
    assert parse_month_html(_table_with_cell(cell), REFERENCE).entries == []


def test_cell_invalid_time_kept_with_none():
    cell = (
        '<td data-id="18" data-group="6511" data-day="5" data-time="broken" '
        'data-month="октябрь"><div class="subject">Математика (лек)</div>'
        '<div class="aud"><b>а.1</b></div>Иванов И. И.<div class="number"></div></td>'
    )
    entries = parse_month_html(_table_with_cell(cell), REFERENCE).entries
    assert len(entries) == 1
    assert entries[0].start_time is None
    assert entries[0].end_time is None


def test_cell_unknown_month_is_skipped():
    cell = (
        '<td data-id="19" data-group="6511" data-day="5" data-time="09:30 - 11:10" '
        'data-month="брюмер"><div class="subject">Математика (лек)</div>'
        '<div class="aud"><b>а.1</b></div>Иванов И. И.<div class="number"></div></td>'
    )
    assert parse_month_html(_table_with_cell(cell), REFERENCE).entries == []


def test_cell_source_number_preserved():
    cell = (
        '<td data-id="20" data-group="6511" data-day="5" data-time="09:30 - 11:10" '
        'data-month="октябрь"><div class="subject">Математика (лек)</div>'
        '<div class="aud"><b>а.1</b></div>Иванов И. И.<div class="number">(21)6</div></td>'
    )
    entries = parse_month_html(_table_with_cell(cell), REFERENCE).entries
    assert entries[0].source_number == "(21)6"


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "name,expected",
    [("октябрь", 10), ("Октября", 10), ("декабрь", 12), ("января", 1), ("брюмер", None)],
)
def test_month_name_to_number(name, expected):
    assert month_name_to_number(name) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [("09:30 - 11:10", (9, 30, 11, 10)), ("14:00–15:40", (14, 0, 15, 40)), ("nope", None)],
)
def test_parse_time_range(raw, expected):
    start, end = parse_time_range(raw)
    if expected is None:
        assert start is None and end is None
    else:
        assert (start.hour, start.minute, end.hour, end.minute) == expected


@pytest.mark.parametrize(
    "subject,expected",
    [("Математика (лек)", "лекция"), ("Труд (лаб)", "лабораторная"), ("Физра (пр)", "практика"),
     ("Курсовая (курс. раб)", "курсовая работа"), ("Без типа", None)],
)
def test_extract_lesson_type(subject, expected):
    assert extract_lesson_type(subject) == expected


def test_strip_lesson_suffix():
    assert strip_lesson_suffix("Математика (лек)") == "Математика"


@pytest.mark.parametrize(
    "month,day,ref,expected_year",
    [
        (10, 6, date(2026, 10, 2), 2026),
        (1, 15, date(2026, 12, 20), 2027),
        (12, 20, date(2027, 1, 5), 2026),
    ],
)
def test_resolve_year(month, day, ref, expected_year):
    assert resolve_year(month, day, ref) == expected_year
