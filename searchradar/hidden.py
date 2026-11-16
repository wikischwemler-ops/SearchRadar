"""Listings the user hid via Telegram – never shown or notified again.

Two ways to hide (processed at the start of the next run, the bot is not online in between):
  * the "🚫 Hide" button under a match message
  * replying to an older match message with  x / weg / hide / ausblenden / /hide
"""
from __future__ import annotations

import json
import os

from .results import now_iso

REPLY_WORDS = {"x", "weg", "hide", "/hide", "ausblenden", "nein", "no", "🚫"}


class Hidden:
    def __init__(self, path: str):
        self.path = path
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            data = {}
        self.items: dict[str, dict] = data.get("hidden", {})
        self.offset: int = int(data.get("telegram_offset", 0))
        self.changed = False

    def __contains__(self, key: str) -> bool:
        return key in self.items

    def add(self, key: str, title: str = "", url: str = "") -> bool:
        if key in self.items:
            return False
        self.items[key] = {"title": title, "url": url, "hidden": now_iso()}
        self.changed = True
        return True

    def save(self) -> None:
        if not self.changed:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"telegram_offset": self.offset, "hidden": self.items}, fh, ensure_ascii=False, indent=1)
            fh.write("\n")


def links_in(message: dict) -> list[str]:
    """URLs of a Telegram message (HTML <a href> arrive as text_link entities)."""
    out = []
    text = message.get("text", "")
    for ent in message.get("entities", []) or []:
        if ent.get("type") == "text_link" and ent.get("url"):
            out.append(ent["url"])
        elif ent.get("type") == "url":
            out.append(text[ent["offset"]:ent["offset"] + ent["length"]])
    return out
