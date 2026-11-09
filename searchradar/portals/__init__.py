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


PORTALS: dict[str, Portal] = {
    p.key: p
    for p in [
        Portal("autoscout24", "AutoScout24", "autoscout24.", autoscout24.parse,
               "sort", {"sort": "age", "desc": "1"}),
        Portal("mobile_de", "mobile.de", "mobile.de", mobile_de.parse,
               "sb", {"sb": "doc", "od": "down"}),
        Portal("kleinanzeigen", "Kleinanzeigen", "kleinanzeigen.de", kleinanzeigen.parse),
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
