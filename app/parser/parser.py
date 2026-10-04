"""HTML parsing for the GTIFEM timetable website.

All site-specific knowledge lives here. If the website changes its markup,
this module (and possibly ``client.py``) is the only place to update.
"""
from __future__ import annotations

import logging
import re
from datetime import date, time

from bs4 import BeautifulSoup, Tag

from app.parser.exceptions import ScheduleStructureError
from app.parser.models import (
    Catalog,
    Course,
    EducationLevel,
    LessonData,
    MonthParseResult,
    Speciality,
)

logger = logging.getLogger(__name__)

MONTHS_NOMINATIVE = {
    "январь": 1,
    "февраль": 2,
    "март": 3,
    "апрель": 4,
    "май": 5,
    "июнь": 6,
    "июль": 7,
    "август": 8,
    "сентябрь": 9,
    "октябрь": 10,
    "ноябрь": 11,
    "декабрь": 12,
}
MONTHS_GENITIVE = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}

LESSON_TYPE_MAP = {
    "лек": "лекция",
    "пр": "практика",
    "сем": "семинар",
    "лаб": "лабораторная",
    "курс. раб": "курсовая работа",
    "курсовая работа": "курсовая работа",
    "консультация": "консультация",
    "практика": "практика",
    "зачет": "зачёт",
    "экзамен": "экзамен",
}

_SUFFIX_RE = re.compile(r"\(([^()]*)\)\s*$")
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*[-–—]\s*(\d{1,2}):(\d{2})")
_PLACEHOLDER_RE = re.compile(r"^[\s.\-–—]*$")


def month_name_to_number(name: str) -> int | None:
    key = name.strip().lower()
    if key in MONTHS_NOMINATIVE:
        return MONTHS_NOMINATIVE[key]
    if key in MONTHS_GENITIVE:
        return MONTHS_GENITIVE[key]
    return None


def resolve_year(month: int, day: int, reference: date) -> int:
    """Pick the year (around ``reference``) that makes the date closest to it."""
    best: tuple[int, int] | None = None
    for year in (reference.year - 1, reference.year, reference.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        distance = abs((candidate - reference).days)
        if best is None or distance < best[0]:
            best = (distance, year)
    return best[1] if best else reference.year


def parse_time_range(value: str) -> tuple[time | None, time | None]:
    match = _TIME_RE.search(value or "")
    if not match:
        return None, None
    sh, sm, eh, em = (int(x) for x in match.groups())
    try:
        return time(sh, sm), time(eh, em)
    except ValueError:
        return None, None


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned or None


def extract_lesson_type(subject_raw: str) -> str | None:
    match = _SUFFIX_RE.search(subject_raw)
    if not match:
        return None
    key = match.group(1).strip().lower()
    return LESSON_TYPE_MAP.get(key)


def strip_lesson_suffix(subject_raw: str) -> str:
    return _SUFFIX_RE.sub("", subject_raw).strip()


# --------------------------------------------------------------------------- #
# Catalog (filters)
# --------------------------------------------------------------------------- #
def parse_catalog(html: str) -> Catalog:
    soup = BeautifulSoup(html, "lxml")
    catalog = Catalog()

    first_section = soup.select_one(".section.first")
    if first_section is None:
        raise ScheduleStructureError("Filter section '.section.first' not found")

    for li in first_section.select("li"):
        anchor = li.find("a")
        if anchor and anchor.get("data-id"):
            catalog.education_levels.append(
                EducationLevel(id=str(anchor["data-id"]), name=anchor.get_text(strip=True))
            )

    if not catalog.education_levels:
        raise ScheduleStructureError("No education levels parsed from '.section.first'")

    for li in soup.select(".section.specials li.special"):
        anchor = li.find("a")
        if anchor is None or not anchor.get("data-id"):
            continue
        education_id = _class_id(li, "special")
        if education_id is None:
            continue
        catalog.specialities.append(
            Speciality(
                id=str(anchor["data-id"]),
                name=anchor.get_text(strip=True),
                education_id=education_id,
            )
        )

    if not catalog.specialities:
        raise ScheduleStructureError("No specialities parsed from '.section.specials'")

    for li in soup.select(".section.courses li.course"):
        special_id = _class_id(li, "course")
        number = li.get("data-course")
        if special_id is None or number is None:
            continue
        anchor = li.find("a")
        name = anchor.get_text(strip=True) if anchor else f"{number} курс"
        try:
            number_int = int(number)
        except (TypeError, ValueError):
            continue
        catalog.courses.append(Course(special_id=special_id, number=number_int, name=name))

    return catalog


def _class_id(tag: Tag, prefix: str) -> str | None:
    for cls in tag.get("class", []) or []:
        if cls.startswith(prefix) and cls[len(prefix):].isdigit():
            return cls[len(prefix):]
    return None


# --------------------------------------------------------------------------- #
# Month table
# --------------------------------------------------------------------------- #
def parse_month_html(html: str, reference: date) -> MonthParseResult:
    """Parse the HTML table fragment returned for one group+month.

    A valid lesson cell always carries ``data-id``, ``data-day``, ``data-time``
    and a non-empty ``.subject``. Empty placeholder cells (which the site also
    emits) are skipped.
    """
    if not html or not html.strip():
        return MonthParseResult(entries=[])

    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if table is None:
        raise ScheduleStructureError("Month response does not contain a <table>")

    header_cells = table.find_all("td", id=re.compile(r"^day\d+$"))
    all_tds = table.find_all("td")
    if not header_cells and not any(td.get("data-id") for td in all_tds):
        raise ScheduleStructureError("Month table has no recognizable day/lesson cells")

    result = MonthParseResult(entries=[])
    result.raw_cells = sum(1 for td in all_tds if td.get("data-id"))

    for td in all_tds:
        if not td.get("data-id"):
            continue
        subject_el = td.find("div", class_="subject")
        subject_raw = clean_text(subject_el.get_text(" ", strip=True)) if subject_el else None
        if not subject_raw:
            continue  # placeholder / empty cell

        day_raw = td.get("data-day")
        month_raw = td.get("data-month") or _caption_month(table)
        if not day_raw or not month_raw:
            logger.debug("Lesson cell without day/month: %s", td.get("data-id"))
            continue
        try:
            day = int(day_raw)
        except ValueError:
            logger.warning("Invalid data-day=%r for source_id=%s", day_raw, td.get("data-id"))
            continue
        month_number = month_name_to_number(month_raw)
        if month_number is None:
            logger.warning("Unknown month name %r", month_raw)
            continue

        year = resolve_year(month_number, day, reference)
        try:
            schedule_date = date(year, month_number, day)
        except ValueError:
            logger.warning("Invalid date %s-%s-%s", year, month_number, day)
            continue

        time_value = td.get("data-time") or _row_time(td)
        start_time, end_time = parse_time_range(time_value)

        classroom = _extract_classroom(td)
        teacher = _extract_teacher(td)
        lesson_type = extract_lesson_type(subject_raw)
        subject = strip_lesson_suffix(subject_raw) if lesson_type else subject_raw
        number_el = td.find("div", class_="number")
        source_number = clean_text(number_el.get_text(" ", strip=True)) if number_el else None
        note = clean_text(td.get("data-not"))

        group_id = clean_text(td.get("data-group")) or ""

        result.entries.append(
            LessonData(
                source_id=str(td["data-id"]).strip(),
                group_id=group_id,
                schedule_date=schedule_date,
                start_time=start_time,
                end_time=end_time,
                subject=subject or None,
                subject_raw=subject_raw,
                teacher=teacher,
                classroom=classroom,
                lesson_type=lesson_type,
                source_number=source_number,
                note=note,
                raw_text=clean_text(td.get_text(" ", strip=True)) or subject_raw,
            )
        )
        result.days.add(day)
        if group_id:
            result.groups.add(group_id)

    return result


def _caption_month(table: Tag) -> str | None:
    caption = table.find("caption")
    if caption:
        return clean_text(caption.get_text(" ", strip=True))
    return None


def _row_time(td: Tag) -> str:
    row = td.find_parent("tr")
    if row is None:
        return ""
    first_cell = row.find("td")
    if first_cell is None or first_cell is td:
        return ""
    return first_cell.get_text(" ", strip=True)


def _extract_classroom(td: Tag) -> str | None:
    aud = td.find("div", class_="aud")
    if aud is None:
        return None
    text = aud.get_text(" ", strip=True)
    if _PLACEHOLDER_RE.match(text or ""):
        return None
    return clean_text(text)


def _extract_teacher(td: Tag) -> str | None:
    clone = BeautifulSoup(str(td), "lxml").find("td")
    if clone is None:
        return None
    for element in clone.find_all("div", class_=["subject", "aud", "number"]):
        element.decompose()
    text = clone.get_text(" ", strip=True)
    if _PLACEHOLDER_RE.match(text or ""):
        return None
    return clean_text(text)
