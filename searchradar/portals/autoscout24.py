"""Parser for AutoScout24 search result pages."""
from __future__ import annotations

import json
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import Listing
from ..utils import clean, find_mileage, find_price, find_year, to_int, year_from_any

BASE = "https://www.autoscout24.de"
NAME = "autoscout24"


def parse(html: str) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[Listing] = []
    seen: set[str] = set()

    for art in soup.select("article[data-guid]"):
        guid = art.get("data-guid")
        if not guid or guid in seen:
            continue
        seen.add(guid)
        a = art.select_one("a[href*='/angebote/']") or art.find("a", href=True)
        url = urljoin(BASE, a["href"]) if a else f"{BASE}/angebote/{guid}"
        h = art.find(["h2", "h3"])
        text = clean(art.get_text(" ", strip=True))
        title = clean(h.get_text(" ", strip=True)) if h else clean(
            f"{art.get('data-make', '')} {art.get('data-model', '')}"
        )
        out.append(
            Listing(
                portal=NAME,
                id=guid,
                url=url,
                title=title,
                price=to_int(art.get("data-price")) or find_price(text),
                mileage=to_int(art.get("data-mileage")) or find_mileage(text),
                year=year_from_any(art.get("data-first-registration")) or find_year(text),
                location=clean(art.get("data-listing-zip-code", "")),
                text=text,
            )
        )

    if not out:
        out = _parse_next_data(soup)
    return out


def _parse_next_data(soup: BeautifulSoup) -> list[Listing]:
    """Fallback: Next.js JSON in <script id="__NEXT_DATA__">."""
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return []
    try:
        data = json.loads(tag.string)
        items = data["props"]["pageProps"]["listings"]
    except (ValueError, KeyError, TypeError):
        return []

    out = []
    for it in items or []:
        lid = str(it.get("id") or "")
        if not lid:
            continue
        v = it.get("vehicle") or {}
        tr = it.get("tracking") or {}
        loc = it.get("location") or {}
        title = clean(f"{v.get('make', '')} {v.get('model', '')} {v.get('modelVersionInput', '')}")
        text = clean(" ".join(str(x) for x in [title, v.get("subtitle", ""), json.dumps(it.get("vehicleDetails", []), ensure_ascii=False)]))
        out.append(
            Listing(
                portal=NAME,
                id=lid,
                url=urljoin(BASE, it.get("url") or f"/angebote/{lid}"),
                title=title,
                price=to_int(tr.get("price")) or to_int((it.get("price") or {}).get("priceFormatted")),
                mileage=to_int(tr.get("mileage")) or to_int(v.get("mileageInKm")),
                year=year_from_any(tr.get("firstRegistration")),
                location=clean(f"{loc.get('zip', '')} {loc.get('city', '')}"),
                text=text,
            )
        )
    return out
