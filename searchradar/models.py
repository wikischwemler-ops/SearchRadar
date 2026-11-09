"""Data model for a single listing found on a portal."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Listing:
    portal: str                 # portal key, e.g. "autoscout24"
    id: str                     # portal-internal listing id
    url: str                    # link to the detail page
    title: str = ""
    price: int | None = None    # EUR
    mileage: int | None = None  # km (vehicles only)
    year: int | None = None     # first registration / model year
    location: str = ""
    text: str = ""              # full text of the result card (used for keyword matching)
    extra: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.portal}:{self.id}"
