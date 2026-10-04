"""Standalone prototype: download one month and print normalized lessons.

Usage examples (PowerShell):
    python scripts/download_and_parse.py --list-catalog
    python scripts/download_and_parse.py --special "Экономика" --course 2 --group "6511,6512" --month октябрь
    python scripts/download_and_parse.py --special "Экономика" --course 2 --group "6511,6512"

The script does not touch the database or Telegram; it only proves the parser.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.parser.client import ScheduleClient
from app.parser.parser import parse_catalog, parse_month_html


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download and parse a month of schedule")
    parser.add_argument("--base", help="Base URL (defaults to SCHEDULE_URL)")
    parser.add_argument("--list-catalog", action="store_true", help="Print the filter catalog")
    parser.add_argument("--special", help="Speciality name, e.g. 'Экономика'")
    parser.add_argument("--course", type=int, help="Course number, e.g. 2")
    parser.add_argument("--group", help="Group code, e.g. '6511,6512'")
    parser.add_argument("--month", help="Month name, e.g. 'октябрь' (default: last available)")
    parser.add_argument("--limit", type=int, default=20, help="How many lessons to print")
    return parser


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    bases = [args.base] if args.base else settings.schedule_bases
    client = ScheduleClient(bases, verify_tls=settings.schedule_tls_verify)
    try:
        if args.list_catalog:
            html = await client.get_catalog_html()
            catalog = parse_catalog(html)
            print("Уровни обучения:")
            for level in catalog.education_levels:
                print(f"  [{level.id}] {level.name}")
                for special in catalog.specialities_for(level.id):
                    courses = ", ".join(str(c.number) for c in catalog.courses_for(special.id))
                    print(f"      [{special.id}] {special.name} — курсы: {courses}")
            return 0

        if not (args.special and args.course and args.group):
            print("Нужны --special, --course и --group (или используйте --list-catalog)")
            return 2

        groups = await client.get_groups(args.special, args.course)
        print(f"Группы для {args.special}, {args.course} курс: {[g.name for g in groups]}")

        months = await client.get_months(args.special, args.course, args.group)
        print(f"Доступные месяцы: {months}")
        month = args.month or (months[-1] if months else None)
        if not month:
            print("Не удалось определить месяц")
            return 1

        html = await client.get_month_html(args.special, args.course, args.group, month)
        result = parse_month_html(html, date.today())
        print(
            f"\nМесяц: {month} | записей: {len(result.entries)} | "
            f"дней: {len(result.days)} | групп: {sorted(result.groups)}"
        )
        for lesson in result.entries[: args.limit]:
            time_range = (
                f"{lesson.start_time.strftime('%H:%M')}-{lesson.end_time.strftime('%H:%M')}"
                if lesson.start_time and lesson.end_time
                else "?"
            )
            print(
                f"{lesson.schedule_date} {time_range:>13} {lesson.group_id} "
                f"{lesson.subject_raw} | {lesson.teacher or '—'} | {lesson.classroom or '—'} "
                f"| {lesson.lesson_type or '—'}"
            )
        return 0
    finally:
        await client.close()


def main() -> None:
    args = build_parser().parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
