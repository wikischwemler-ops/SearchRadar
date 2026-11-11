"""Loads settings.json and every topic file in searches/*.json."""
from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass, field

DEFAULT_SETTINGS = {
    "notify_on_first_run": False,
    "max_notifications_per_run": 30,
    "max_detail_checks_per_run": 25,
    "request_delay_seconds": [3, 7],
    "alerts_thread_id": None,   # Telegram topic for warnings (None = General)
    "max_rechecks_per_run": 40, # stored matches re-visited per run (still online? price?)
    "notify_price_drops": True, # Telegram message when a stored match gets cheaper
}


@dataclass
class Search:
    id: str            # "<topic file>/<name>" - used as key in state
    name: str
    urls: list[str]
    filters: dict


@dataclass
class Topic:
    file: str
    topic: str
    emoji: str = "📡"
    telegram_thread_id: int | None = None
    telegram_chat_id: str | None = None
    enabled: bool = True
    defaults: dict = field(default_factory=dict)
    searches: list[Search] = field(default_factory=list)


LIST_KEYS = ("must_contain", "must_not_contain", "title_must_contain", "require_known")


def merge_filters(defaults: dict, own: dict) -> dict:
    """Search filters override defaults; keyword lists are combined instead of replaced."""
    merged = {**defaults, **own}
    for key in LIST_KEYS:
        if key in defaults and key in own:
            merged[key] = list(defaults[key]) + [x for x in own[key] if x not in defaults[key]]
    return merged


def _load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except ValueError as exc:
            raise ValueError(f"{path}: invalid JSON – {exc}") from exc


def load_settings(path: str) -> dict:
    s = dict(DEFAULT_SETTINGS)
    if os.path.exists(path):
        s.update({k: v for k, v in _load_json(path).items() if not k.startswith("_")})
    return s


def load_topics(directory: str) -> list[Topic]:
    topics = []
    for path in sorted(glob.glob(os.path.join(directory, "*.json"))):
        raw = _load_json(path)
        stem = os.path.splitext(os.path.basename(path))[0]
        t = Topic(
            file=stem,
            topic=raw.get("topic", stem),
            emoji=raw.get("emoji", "📡"),
            telegram_thread_id=raw.get("telegram_thread_id"),
            telegram_chat_id=raw.get("telegram_chat_id"),
            enabled=raw.get("enabled", True),
            defaults=raw.get("defaults", {}),
        )
        for s in raw.get("searches", []):
            if not s.get("enabled", True):
                continue
            if "name" not in s or not s.get("urls"):
                raise ValueError(f"{path}: every search needs 'name' and 'urls'")
            filters = merge_filters(t.defaults, s.get("filters", {}))
            t.searches.append(Search(id=f"{stem}/{s['name']}", name=s["name"],
                                     urls=s["urls"], filters=filters))
        topics.append(t)
    return topics
