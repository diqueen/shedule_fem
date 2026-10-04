"""Download real HTML fixtures from the schedule site for tests.

This script talks to the live site. It is only used to (re)generate the
fixtures under tests/fixtures/. Tests themselves never touch the network.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlencode

import httpx

BASE = "https://gtifem.technolog.edu.ru/dekanat/raspisanie/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded",
}
OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with httpx.Client(verify=False, timeout=60, follow_redirects=True, headers=HEADERS) as c:
        page = c.get(BASE).text
        (OUT / "main_page.html").write_text(page, encoding="utf-8")

        def post(data: dict) -> str:
            return c.post(BASE, content=urlencode(data).encode()).text

        groups = post({"special": "Экономика", "course": "2"})
        (OUT / "groups.json").write_text(groups, encoding="utf-8")
        months = post({"special": "Экономика", "course": "2", "group": "6511,6512"})
        (OUT / "months.json").write_text(months, encoding="utf-8")

        october = post({
            "special": "Экономика", "course": "2", "group": "6511,6512", "month": "октябрь",
        })
        (OUT / "schedule_october.html").write_text(october, encoding="utf-8")

        september = post({
            "special": "Экономика", "course": "2", "group": "6511,6512", "month": "сентябрь",
        })
        (OUT / "schedule_september.html").write_text(september, encoding="utf-8")

        # Group 6611 (Экономика, 1st course) has "День знаний" and single-number cells.
        first = post({
            "special": "Экономика", "course": "1", "group": "6611", "month": "сентябрь",
        })
        (OUT / "schedule_september_6611.html").write_text(first, encoding="utf-8")

        # Synthetic November fixture (site only exposes September/October right now).
        november = october.replace("октябрь", "ноябрь").replace("Октября", "Ноября")
        (OUT / "schedule_november.html").write_text(november, encoding="utf-8")

        meta = {
            "source": BASE,
            "months": json.loads(months),
            "note": "Real responses captured from gtifem.ru mirror; november is synthetic.",
        }
        (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("fixtures written to", OUT)


if __name__ == "__main__":
    main()
