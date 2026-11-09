"""Active matches with price history (state/matches.json) – the data source for the web overview and RESULTS.md.

- A match stays as long as the listing is online. It is removed after it was found to be gone
  in GONE_CONFIRMATIONS consecutive checks (one check can be a hiccup).
- Every price change is appended to `history` as [timestamp, price]. The chart draws a step line
  from these points up to `last_checked`, so "price unchanged" needs no extra points.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from .models import Listing
from .portals import label

GONE_CONFIRMATIONS = 2
MAX_HISTORY = 200


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Results:
    def __init__(self, path: str):
        self.path = path
        self.items: dict[str, dict] = {}
        self.removed: list[dict] = []
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    self.items = {m["id"]: m for m in json.load(fh).get("matches", [])}
            except (ValueError, KeyError):
                self.items = {}

    @staticmethod
    def make_id(search_id: str, listing_key: str) -> str:
        return f"{search_id}|{listing_key}"

    def get(self, search_id: str, listing_key: str) -> dict | None:
        return self.items.get(self.make_id(search_id, listing_key))

    def add(self, topic_file: str, topic: str, emoji: str, search_id: str, search: str,
            l: Listing, keywords: list[str]) -> None:
        mid = self.make_id(search_id, l.key)
        if mid in self.items:
            return
        ts = now_iso()
        self.items[mid] = {
            "id": mid,
            "listing_id": l.id,
            "found": ts,
            "last_seen": ts,
            "last_checked": ts,
            "gone_count": 0,
            "topic_file": topic_file,
            "topic": topic,
            "emoji": emoji,
            "search": search,
            "portal": label(l.portal),
            "title": l.title,
            "url": l.url,
            "price": l.price,
            "mileage": l.mileage,
            "year": l.year,
            "location": l.location,
            "keywords": keywords,
            "history": [[ts, l.price]] if l.price is not None else [],
        }

    def update_price(self, m: dict, price: int | None) -> tuple[int, int] | None:
        """Marks the match as alive and records a price change. Returns (old, new) if the price changed."""
        ts = now_iso()
        m["last_seen"] = m["last_checked"] = ts
        m["gone_count"] = 0
        if price is None or price == m.get("price"):
            return None
        old = m.get("price")
        m["price"] = price
        m.setdefault("history", []).append([ts, price])
        m["history"] = m["history"][-MAX_HISTORY:]
        return (old, price) if old is not None else None

    def mark_gone(self, m: dict) -> bool:
        """Returns True if the match was removed."""
        m["last_checked"] = now_iso()
        m["gone_count"] = m.get("gone_count", 0) + 1
        if m["gone_count"] >= GONE_CONFIRMATIONS:
            self.removed.append(self.items.pop(m["id"]))
            return True
        return False

    def touch(self, m: dict) -> None:
        m["last_checked"] = now_iso()

    def due_for_check(self, exclude_seen_since: str) -> list[dict]:
        """Matches not seen on a result page in this run, oldest check first."""
        return sorted((m for m in self.items.values() if m.get("last_seen", "") < exclude_seen_since),
                      key=lambda m: m.get("last_checked", ""))

    def sorted(self) -> list[dict]:
        return sorted(self.items.values(), key=lambda m: m["found"], reverse=True)

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"updated": now_iso(), "matches": self.sorted()}, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
