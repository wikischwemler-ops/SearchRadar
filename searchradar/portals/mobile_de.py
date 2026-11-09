"""Parser for mobile.de search result pages.

mobile.de renders heavily with JavaScript and uses strong bot protection.
The parser therefore looks generically for links to detail pages
(details.html?id=...) and reads the surrounding result card.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import Listing
from ..utils import clean, find_mileage, find_price, find_year

BASE = "https://suchen.mobile.de"
NAME = "mobile_de"
_ID_RE = re.compile(r"details\.html\?(?:.*&)?id=(\d+)")


def parse(html: str) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[Listing] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=_ID_RE):
        m = _ID_RE.search(a["href"])
        lid = m.group(1)
        if lid in seen:
            continue
        # card = the link itself or the closest container that shows a price
        card = a
        for parent in [a, *a.parents][:6]:
            if "€" in parent.get_text():
                card = parent
                break
        text = clean(card.get_text(" ", strip=True))
        if not text:
            continue
        seen.add(lid)
        h = card.find(["h2", "h3"])
        title = clean(h.get_text(" ", strip=True)) if h else text[:80]
        out.append(
            Listing(
                portal=NAME,
                id=lid,
                url=f"{BASE}/fahrzeuge/details.html?id={lid}",
                title=title,
                price=find_price(text),
                mileage=find_mileage(text),
                year=find_year(text),
                text=text,
            )
        )
    return out
