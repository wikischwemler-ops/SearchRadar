"""Parser for Kleinanzeigen.de search result pages (works for every category)."""
from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import Listing
from ..utils import clean, find_mileage, find_year, to_int, year_from_tag

BASE = "https://www.kleinanzeigen.de"
NAME = "kleinanzeigen"


def parse(html: str) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[Listing] = []
    seen: set[str] = set()

    for art in soup.select("article.aditem[data-adid]"):
        adid = art.get("data-adid")
        if not adid or adid in seen:
            continue
        seen.add(adid)

        href = art.get("data-href")
        a = art.select_one("h2 a, a.ellipsis, a[href*='/s-anzeige/']")
        if not href and a:
            href = a.get("href")
        url = urljoin(BASE, href) if href else f"{BASE}/s-anzeige/{adid}"

        title = clean(a.get_text(" ", strip=True)) if a else ""
        price_el = art.select_one(".aditem-main--middle--price-shipping--price, .aditem-main--middle--price")
        loc_el = art.select_one(".aditem-main--top--left")
        tags = [clean(t.get_text(" ", strip=True)) for t in art.select(".simpletag, .aditem-main--bottom span")]
        text = clean(art.get_text(" ", strip=True))

        year = find_year(" ".join(tags)) or next((y for y in map(year_from_tag, tags) if y), None) or find_year(text)

        out.append(
            Listing(
                portal=NAME,
                id=adid,
                url=url,
                title=title,
                price=to_int(price_el.get_text()) if price_el else None,
                mileage=find_mileage(" ".join(tags)) or find_mileage(text),
                year=year,
                location=clean(loc_el.get_text(" ", strip=True)) if loc_el else "",
                text=text,
            )
        )
    return out
