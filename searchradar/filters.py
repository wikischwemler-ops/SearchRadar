"""Minimum criteria: numeric limits, required and excluded keywords.

A listing is only reported if it passes EVERY configured criterion.
"""
from __future__ import annotations

import re
from functools import lru_cache

from .models import Listing

NUMERIC = {
    # filter key: (listing attribute, comparison)
    "min_price": ("price", "min"),
    "max_price": ("price", "max"),
    "min_mileage": ("mileage", "min"),
    "max_mileage": ("mileage", "max"),
    "min_year": ("year", "min"),
    "max_year": ("year", "max"),
}


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


@lru_cache(maxsize=2048)
def _pattern(term: str) -> re.Pattern:
    # match at the START of a word: "Pano" hits "Panoramadach", "suche" does not hit "versuche"
    return re.compile(r"(?<!\w)" + re.escape(_norm(term)))


def has(text_norm: str, term: str) -> bool:
    return bool(_pattern(term).search(text_norm))


def _alts(req) -> list[str]:
    return req if isinstance(req, list) else [req]


def check_basic(listing: Listing, f: dict) -> tuple[bool, str]:
    """Numeric limits, `require_known` and excluded words on the result card."""
    for field_name in f.get("require_known", []):
        if getattr(listing, field_name, None) in (None, ""):
            return False, f"{field_name} unknown"
    for key, (attr, op) in NUMERIC.items():
        limit = f.get(key)
        value = getattr(listing, attr)
        if limit is None or value is None:
            continue  # unknown values pass unless listed in require_known
        if (op == "max" and value > limit) or (op == "min" and value < limit):
            return False, f"{attr} {value} violates {key}={limit}"
    bad = excluded_by(f"{listing.title} {listing.text}", f)
    if bad:
        return False, f"contains '{bad}'"
    return True, ""


def missing_keywords(text: str, f: dict) -> list[str]:
    """Required keywords that are missing. An entry may be a string or a list of alternatives."""
    t = _norm(text)
    return [" / ".join(_alts(r)) for r in f.get("must_contain", [])
            if not any(has(t, a) for a in _alts(r))]


def missing_title_keywords(title: str, f: dict) -> list[str]:
    t = _norm(title)
    return [" / ".join(_alts(r)) for r in f.get("title_must_contain", [])
            if not any(has(t, a) for a in _alts(r))]


def excluded_by(text: str, f: dict) -> str | None:
    t = _norm(text)
    return next((w for w in f.get("must_not_contain", []) if has(t, w)), None)


def found_keywords(text: str, f: dict) -> list[str]:
    """Which required keywords were found (shown in the Telegram message)."""
    t = _norm(text)
    out = []
    for r in f.get("must_contain", []):
        hit = next((a for a in _alts(r) if has(t, a)), None)
        if hit:
            out.append(hit)
    return out
