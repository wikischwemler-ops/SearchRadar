"""Small helpers for parsing numbers and text."""
from __future__ import annotations

import re

_KM_RE = re.compile(r"(\d{1,3}(?:[.  ]\d{3})+|\d{1,7})\s*km\b", re.IGNORECASE)
_PRICE_RE = re.compile(r"(\d{1,3}(?:[.  ]\d{3})+|\d{3,7})\s*(?:,-|,00)?\s*€")
_EZ_RE = re.compile(r"\b(?:EZ\s*)?(?:0?[1-9]|1[0-2])\s*/\s*((?:19|20)\d{2})\b")
_YEAR_ONLY_RE = re.compile(r"^\s*(?:EZ\s*)?((?:19|20)\d{2})\s*$", re.IGNORECASE)


def to_int(value) -> int | None:
    """'12.990 € VB' -> 12990, '45.000 km' -> 45000, None/'' -> None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^\d]", "", str(value).split(",")[0])
    return int(digits) if digits else None


def find_mileage(text: str) -> int | None:
    m = _KM_RE.search(text or "")
    return to_int(m.group(1)) if m else None


def find_price(text: str) -> int | None:
    m = _PRICE_RE.search(text or "")
    return to_int(m.group(1)) if m else None


def find_year(text: str) -> int | None:
    """Finds first registration like 'EZ 05/2020' or '05/2020'."""
    m = _EZ_RE.search(text or "")
    return int(m.group(1)) if m else None


def year_from_tag(tag: str) -> int | None:
    """A tag consisting only of a year ('2019' or 'EZ 2019')."""
    m = _YEAR_ONLY_RE.match(tag or "")
    return int(m.group(1)) if m else None


def year_from_any(value) -> int | None:
    """'03-2021', '2021-03', '03/2021', 2021 -> 2021."""
    if value is None:
        return None
    m = re.search(r"((?:19|20)\d{2})", str(value))
    return int(m.group(1)) if m else None


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def fmt_int(n: int | None) -> str:
    return f"{n:,}".replace(",", ".") if n is not None else "?"
