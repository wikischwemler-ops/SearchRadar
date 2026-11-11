"""Parser for Kleinanzeigen.de search result pages (works for every category).

Supports the current layout (2026: <article data-adid> with utility CSS classes, title in <h3>)
and the older one (<article class="aditem">, title in <h2>).
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import Listing
from ..utils import clean, find_mileage, find_price, find_year, to_int, year_from_tag

BASE = "https://www.kleinanzeigen.de"
NAME = "kleinanzeigen"

_PLZ_RE = re.compile(r"^\d{5}\s+\S")
_PAREN_RE = re.compile(r"\([^)]*\)")


def _price(art) -> int | None:
    # old layout
    el = art.select_one(".aditem-main--middle--price-shipping--price, .aditem-main--middle--price")
    if el:
        return to_int(el.get_text())
    # new layout: first price element that is not the struck-through old price
    for el in art.find_all(["p", "span", "div"]):
        txt = el.get_text(" ", strip=True)
        if "€" in txt and len(txt) < 30 and not el.find(["p", "span", "div"]):
            if "line-through" in " ".join(el.get("class") or []):
                continue
            return find_price(txt) or to_int(txt)
    return None


def _location(art) -> str:
    el = art.select_one(".aditem-main--top--left")
    if el:
        return clean(el.get_text(" ", strip=True))
    for el in art.find_all(["span", "div"]):
        txt = clean(el.get_text(" ", strip=True))
        if len(txt) < 60 and _PLZ_RE.match(txt) and not el.find(["span", "div"]):
            return txt
    return ""


def parse(html: str) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[Listing] = []
    seen: set[str] = set()

    # Only the real result list: "#srchrslt-adtable-altads" holds nationwide "alternative" ads
    # that ignore the location/radius and filters of the search.
    main = soup.select_one("#srchrslt-adtable") or soup
    for art in main.select("article[data-adid]"):
        if art.find_parent(id="srchrslt-adtable-altads"):
            continue
        adid = art.get("data-adid")
        if not adid or adid in seen:
            continue
        seen.add(adid)
        for s in art.find_all(["script", "style", "svg"]):
            s.decompose()

        href = art.get("data-href")
        heading = art.find(["h2", "h3"])
        link = (heading.find("a") if heading else None) or art.select_one("a.ellipsis") or next(
            (a for a in art.select("a[href*='/s-anzeige/']") if clean(a.get_text())
             and not clean(a.get_text()).isdigit()), None)
        if not href and link:
            href = link.get("href")
        url = urljoin(BASE, href) if href else f"{BASE}/s-anzeige/{adid}"

        title = clean((heading or link).get_text(" ", strip=True)) if (heading or link) else ""
        tags = [clean(t.get_text(" ", strip=True)) for t in art.select(".simpletag, .aditem-main--bottom span")]
        if not tags:  # new layout: short leaf <span> badges like "90.000 km", "EZ 11/2016", "Gesuch"
            tags = [clean(t.get_text(" ", strip=True)) for t in art.find_all("span")
                    if not t.find(["span", "div", "p"]) and 0 < len(t.get_text(strip=True)) < 25]
            tags = [t for t in tags if not t.startswith("(")]  # "(9 km)" is the distance, not mileage
        text = clean(art.get_text(" ", strip=True))
        year = (find_year(" ".join(tags)) or next((y for y in map(year_from_tag, tags) if y), None)
                or find_year(text))

        out.append(
            Listing(
                portal=NAME,
                id=adid,
                url=url,
                title=title,
                price=_price(art),
                mileage=next((m for m in map(find_mileage, tags) if m), None) or find_mileage(_PAREN_RE.sub(" ", text)),
                year=year,
                location=_location(art),
                text=text,
                extra={"wanted": "Gesuch" in tags or " Gesuch " in f" {text} "},
            )
        )
    return out
