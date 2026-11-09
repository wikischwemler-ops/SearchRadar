"""Remembers which listings were already seen (state/seen.json)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

KEEP_DAYS = 90


def _now() -> datetime:
    return datetime.now(timezone.utc)


class State:
    def __init__(self, path: str):
        self.path = path
        data = {}
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh) or {}
            except ValueError:
                data = {}
        self.seen: dict[str, dict] = data.get("seen", {})
        self.errors: dict[str, int] = data.get("errors", {})
        self.initialized: list[str] = data.get("initialized_searches", [])

    @staticmethod
    def key(search_id: str, listing_key: str) -> str:
        return f"{search_id}|{listing_key}"

    def is_seen(self, search_id: str, listing_key: str) -> bool:
        return self.key(search_id, listing_key) in self.seen

    def mark(self, search_id: str, listing_key: str, matched: bool) -> None:
        self.seen[self.key(search_id, listing_key)] = {
            "t": _now().isoformat(timespec="seconds"), "m": matched}

    def prune(self) -> None:
        cutoff = _now() - timedelta(days=KEEP_DAYS)
        self.seen = {k: v for k, v in self.seen.items()
                     if datetime.fromisoformat(v.get("t", _now().isoformat())) >= cutoff}

    def save(self) -> None:
        self.prune()
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"seen": dict(sorted(self.seen.items())), "errors": self.errors,
                       "initialized_searches": sorted(set(self.initialized))},
                      fh, ensure_ascii=False, indent=1)
            fh.write("\n")
