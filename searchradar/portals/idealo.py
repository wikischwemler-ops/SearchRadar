"""Parser for idealo.de product pages (price comparison for NEW goods).

One product page -> one "listing": the product with idealo's lowest current price
(JSON-LD AggregateOffer.lowPrice). Matches are stored like any listing, so every run
updates the price history and a cheaper price triggers a price-drop message.

Example URL: https://www.idealo.de/preisvergleich/OffersOfProduct/209644835_-rally-rs210-powermeter-pedale-garmin.html
"""
from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from ..models import Listing
from ..utils import clean

NAME = "idealo"
_ID_RE = re.compile(r"OffersOfProduct/(\d+)")


def _products(soup):
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except ValueError:
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if node.get("@type") in ("Product", "ProductGroup"):
                    yield node
                stack.extend(v for v in node.values() if isinstance(v, (dict, list)))
            elif isinstance(node, list):
                stack.extend(node)


def parse(html: str) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    name, low, url, pid, count = "", None, "", "", None
    for p in _products(soup):
        name = name or p.get("name", "")
        url = url or p.get("url") or p.get("@id") or ""
        pid = pid or str(p.get("productGroupID") or "")
        offers = p.get("offers")
        if isinstance(offers, dict) and offers.get("lowPrice") not in (None, ""):
            price = int(float(offers["lowPrice"]) + 0.5)
            low = price if low is None else min(low, price)
            count = count or offers.get("offerCount")
    if not url:
        canon = soup.find("link", rel="canonical") or soup.find("meta", property="og:url")
        url = (canon.get("href") or canon.get("content") or "") if canon else ""
    m = _ID_RE.search(url)
    pid = pid or (m.group(1) if m else "")
    if not pid or not name or low is None:
        return []
    name = clean(re.sub(r"<[^>]+>", "", name))
    offers_txt = f" · {count} offers" if count else ""
    return [Listing(portal=NAME, id=pid, url=url, title=name, price=low,
                    text=f"{name} new, lowest price on idealo{offers_txt}", extra={"new": True})]
