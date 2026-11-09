"""Telegram notifications, optionally into forum topics (message_thread_id)."""
from __future__ import annotations

import html
import json
import os
import time
import urllib.error
import urllib.request

from .models import Listing
from .portals import label
from .utils import fmt_int


class Telegram:
    def __init__(self, dry_run: bool = False):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.configured = bool(self.token and self.chat_id)
        self.dry_run = dry_run or not self.configured

    def send(self, text: str, thread_id: int | None = None, chat_id: str | None = None) -> bool:
        if self.dry_run:
            where = f" -> topic {thread_id}" if thread_id else ""
            print(f"---- Telegram (dry-run){where} ----\n{text}\n" + "-" * 30)
            return True
        body = {"chat_id": chat_id or self.chat_id, "text": text,
                "parse_mode": "HTML", "disable_web_page_preview": False}
        if thread_id:
            body["message_thread_id"] = int(thread_id)
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{self.token}/sendMessage",
            data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=20) as r:
                    ok = json.load(r).get("ok", False)
                time.sleep(1.1)  # Telegram limit: ~1 message/second per chat
                return ok
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode(errors="replace")[:300]
                print(f"Telegram error (attempt {attempt + 1}): {exc} {detail}")
                if exc.code == 429:
                    time.sleep(10)
                elif 400 <= exc.code < 500:
                    return False  # wrong chat/thread id etc. - retrying won't help
            except Exception as exc:  # noqa: BLE001
                print(f"Telegram error (attempt {attempt + 1}): {exc}")
                time.sleep(3)
        return False


def format_listing(topic: str, search_name: str, l: Listing, keywords: list[str], emoji: str = "📡") -> str:
    e = html.escape
    lines = [f"{emoji} <b>{e(search_name)}</b>", f"<b>{e(l.title or 'Listing')}</b>"]
    facts = []
    if l.price is not None:
        facts.append(f"💶 {fmt_int(l.price)} €")
    if l.mileage is not None:
        facts.append(f"🛣 {fmt_int(l.mileage)} km")
    if l.year is not None:
        facts.append(f"📅 {l.year}")
    if facts:
        lines.append(" · ".join(facts))
    if l.location:
        lines.append(f"📍 {e(l.location)}")
    if keywords:
        lines.append(f"✅ {e(', '.join(keywords))}")
    lines.append(f'🔗 <a href="{e(l.url, quote=True)}">Open on {e(label(l.portal))}</a>')
    lines.append(f"<i>#{e(topic.replace(' ', '_'))}</i>")
    return "\n".join(lines)
