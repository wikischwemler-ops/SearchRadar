"""Parser for eBay.de search result pages (2026 layout: <li class="s-card" data-listingid>).

Example search URL (newest first, items located in Germany):
  https://www.ebay.de/sch/i.html?_nkw=adidas+terrex&_sop=10&LH_PrefLoc=1
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..models import Listing
from ..utils import clean, to_int

NAME = "ebay"
_ID_RE = re.compile(r"/itm/(?:[^/?]+/)?(\d{9,})")


def parse(html: str) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "svg"]):
        t.decompose()
    out, seen = [], set()
    for card in soup.select("li.s-card[data-listingid], li.s-item"):
        link = None
        for a in card.select("a[href*='/itm/']"):
            if "ebay.de" in a["href"] or a["href"].startswith("/"):
                link = a
                break
        if link is None:
            continue  # "Shop on eBay" placeholder (ebay.com/itm/123456) and ads
        m = _ID_RE.search(link["href"])
        if not m or m.group(1) in seen:
            continue
        item_id = m.group(1)
        seen.add(item_id)

        title_el = card.select_one(".s-card__title .primary, .s-card__title, .s-item__title")
        if title_el is not None:
            for junk in title_el.select(".s-card__new-listing, .clipped, .LIGHT_HIGHLIGHT"):
                junk.decompose()
        title = clean(title_el.get_text(" ", strip=True)) if title_el else ""
        title = re.sub(r"^(Neues Angebot|NEUES ANGEBOT)\s*", "", title)

        price_el = card.select_one(".s-card__price, .s-item__price")
        price = to_int(price_el.get_text()) if price_el else None

        text = clean(card.get_text(" ", strip=True))
        auction = bool(re.search(r"\d+\s+Gebot", text))
        out.append(Listing(
            portal=NAME, id=item_id, url=f"https://www.ebay.de/itm/{item_id}", title=title,
            price=price, text=text, extra={"auction": True} if auction else {},
        ))
    return out
