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
_BADGES_RE = re.compile(r"^(?:\s*(?:Gesponsert|NEU|Top)\s*)+")
_LOC_RE = re.compile(r"\b\d{5}\s+[A-ZÄÖÜ][\wäöüß .()/-]{1,40}?(?=\s+(?:\d|Kontakt|Parken|\(|$)|$)")


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
        title = _BADGES_RE.sub("", title).strip()
        price_el = card.select_one("[data-testid='main-price-label'], [data-testid='price-label']")
        loc_el = card.select_one("[class*='dealerLocation'], [class*='Location']")
        loc = None if loc_el else _LOC_RE.search(text)
        out.append(
            Listing(
                portal=NAME,
                id=lid,
                url=f"{BASE}/fahrzeuge/details.html?id={lid}",
                title=title,
                price=find_price(price_el.get_text(" ", strip=True)) if price_el else find_price(text),
                mileage=find_mileage(text),
                year=find_year(text),
                location=clean(loc_el.get_text(" ", strip=True)) if loc_el else (loc.group(0).strip() if loc else ""),
                text=text,
            )
        )
    return out
