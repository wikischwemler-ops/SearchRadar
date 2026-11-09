"""Portal registry.

To add a new portal:
  1. create searchradar/portals/<name>.py with   parse(html: str) -> list[Listing]
  2. register it in PORTALS below (label, domain fragment, optional sort params)
  3. add a test with a small HTML sample in tests/
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from ..models import Listing
from . import autoscout24, kleinanzeigen, mobile_de


@dataclass(frozen=True)
class Portal:
    key: str
    label: str
    domain: str                                   # matched against the URL host
    parse: Callable[[str], list[Listing]]
    sort_param: str | None = None                 # if missing in URL -> add newest-first sort
    sort_value: dict = field(default_factory=dict)
    # CSS selectors of the listing's OWN content on a detail page (title, attributes, description).
    # Only these are searched, so "similar listings" on the page can't cause false matches.
    # If none of them is found, the whole page minus nav/footer/recommendations is used.
    detail_selectors: tuple = ()


PORTALS: dict[str, Portal] = {
    p.key: p
    for p in [
        Portal("autoscout24", "AutoScout24", "autoscout24.", autoscout24.parse,
               "sort", {"sort": "age", "desc": "1"},
               ("h1", "[class*='StageTitle']", "[class*='VehicleOverview']", "[class*='DetailsSection']",
                "[data-cy*='equipment']", "[data-cy*='seller-notes']", "[data-cy*='basic-details']",
                "[data-cy*='technical-details']")),
        Portal("mobile_de", "mobile.de", "mobile.de", mobile_de.parse,
               "sb", {"sb": "doc", "od": "down"},
               ("h1", "#ad-title", "[data-testid*='technical-data']", "[data-testid*='features']",
                "[data-testid*='description']", ".description")),
        Portal("kleinanzeigen", "Kleinanzeigen", "kleinanzeigen.de", kleinanzeigen.parse,
               detail_selectors=("#viewad-title", "#viewad-price", "#viewad-details", "#viewad-configuration",
                                 "#viewad-description-text", ".addetailslist", ".checktaglist")),
    ]
}


def detect_portal(url: str) -> Portal:
    host = urlparse(url).netloc.lower()
    for p in PORTALS.values():
        if p.domain in host:
            return p
    raise ValueError(f"Unsupported portal: {url}")


def newest_first(url: str, portal: Portal) -> str:
    """Add a 'newest first' sort order if the URL has none."""
    if not portal.sort_param:
        return url
    p = urlparse(url)
    q = parse_qs(p.query, keep_blank_values=True)
    if portal.sort_param in q:
        return url
    q.update({k: [v] for k, v in portal.sort_value.items()})
    return urlunparse(p._replace(query=urlencode(q, doseq=True)))


def label(portal_key: str) -> str:
    p = PORTALS.get(portal_key)
    return p.label if p else portal_key


# ---- detail-page checks (used to re-check stored matches) ----------------------------

import json as _json
import re as _re

from bs4 import BeautifulSoup as _BS

from ..utils import to_int as _to_int

GONE_MARKERS = (
    "nicht mehr verfügbar", "nicht mehr online", "wurde gelöscht", "wurde deaktiviert",
    "anzeige ist nicht mehr", "inserat ist nicht mehr", "fahrzeug ist nicht mehr",
    "existiert nicht mehr", "bereits verkauft", "no longer available", "has been removed",
    "listing has expired", "seite wurde nicht gefunden", "page not found",
)

TITLE_GONE_MARKERS = ("gelöscht", "verkauft", "sold", "deaktiviert")

PRICE_SELECTORS = {
    "kleinanzeigen": ("#viewad-price", "[itemprop='price']"),
    "autoscout24": ("[data-testid='price-label']", "[class*='PriceInfo_price']", "[class*='Price_price']"),
    "mobile_de": ("[data-testid='prime-price']", "[data-testid*='price'] span", ".price-block"),
}


def _jsonld_price(soup) -> int | None:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = _json.loads(tag.string or "")
        except ValueError:
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                offers = node.get("offers")
                if isinstance(offers, dict) and offers.get("price") not in (None, ""):
                    return _to_int(str(offers["price"]).split(".")[0])
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
    return None


def check_detail(status: int, final_url: str, html: str, portal: Portal, listing_id: str) -> tuple[bool, int | None]:
    """Returns (gone, current_price) for a detail page."""
    if status in (404, 410):
        return True, None
    # redirected to a page that no longer contains the listing id (typically the search page)
    if listing_id and listing_id.lower() not in final_url.lower():
        return True, None
    soup = _BS(html, "html.parser")
    for t in soup(["script", "style", "noscript", "nav", "footer"]):
        if t.name != "script" or t.get("type") != "application/ld+json":
            t.decompose()
    own = [el for sel in portal.detail_selectors for el in soup.select(sel)]
    if own:
        # listing content is present -> only the title may say it's gone ("Gelöscht • …", "VERKAUFT")
        title_el = soup.find("h1") or own[0]
        title = title_el.get_text(" ", strip=True).lower()
        if any(m in title for m in TITLE_GONE_MARKERS):
            return True, None
    else:
        text = " ".join(soup.get_text(" ", strip=True).lower().split())[:20000]
        if any(m in text for m in GONE_MARKERS):
            return True, None
    price = _jsonld_price(soup)
    if price is None:
        for sel in PRICE_SELECTORS.get(portal.key, ()):
            el = soup.select_one(sel)
            if el:
                m = _re.search(r"\d[\d.\s]*", el.get_text(" ", strip=True))
                price = _to_int(m.group(0)) if m else None
                if price:
                    break
    return False, price
