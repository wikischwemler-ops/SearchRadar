"""Entry point: python -m searchradar [--dry-run] [--topic cars] ..."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

from bs4 import BeautifulSoup

from . import filters
from .config import Search, Topic, load_settings, load_topics
from .http import Fetcher
from .models import Listing
from .portals import check_detail, detect_portal, newest_first
from .results import Results, now_iso
from .utils import fmt_int
from .state import State
from .telegram import Telegram, format_listing

ERROR_ALERT_AFTER = 3     # warn after N consecutive failures
ERROR_REPEAT_EVERY = 24   # then at most about once a day


_NOISE = ("similar", "recommend", "related", "carousel", "teaser", "promo", "other-ads", "weitere",
          "cookie", "consent", "footer", "header", "breadcrumb", "banner")


def page_text(html: str, selectors: tuple = ()) -> str:
    """Text of a detail page – only the listing's own content, not recommendations."""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "svg", "form"]):
        t.decompose()
    if selectors:
        parts = []
        for sel in selectors:
            parts += [el.get_text(" ", strip=True) for el in soup.select(sel)]
        if parts:
            return " ".join(parts)
    for el in soup.find_all(True):
        if el.decomposed:
            continue
        marker = " ".join([el.get("id") or "", *(el.get("class") or []), el.get("data-testid") or ""]).lower()
        if marker and any(n in marker for n in _NOISE):
            el.decompose()
    return soup.get_text(" ", strip=True)


class Runner:
    def __init__(self, args, settings: dict):
        self.args = args
        self.s = settings
        self.state = State(args.state)
        self.results = Results(args.matches)
        self.run_start = now_iso()
        self.topics_by_file: dict[str, Topic] = {}
        self.tg = Telegram(dry_run=args.dry_run)
        self.fetcher = Fetcher(delay=tuple(settings["request_delay_seconds"]))  # type: ignore[arg-type]
        self.detail_budget = int(settings["max_detail_checks_per_run"])
        self.notify_budget = int(settings["max_notifications_per_run"])
        self.sent = 0
        self.summary: list[str] = []

    def log(self, msg: str) -> None:
        if self.args.verbose:
            print(msg)

    def alert(self, text: str) -> None:
        self.tg.send(text, thread_id=self.s.get("alerts_thread_id"))

    # ---- per search -------------------------------------------------------
    def run_search(self, topic: Topic, search: Search) -> None:
        sid = search.id
        first_run = sid not in self.state.initialized and not self.s["notify_on_first_run"]
        if first_run:
            print(f"[{sid}] first run: existing listings are marked as seen silently")
        found = new = matched = 0

        for raw_url in search.urls:
            try:
                portal = detect_portal(raw_url)
            except ValueError as exc:
                print(f"[{sid}] {exc}")
                continue
            try:
                listings = portal.parse(self.fetcher.get(newest_first(raw_url, portal)))
                if not listings:
                    raise RuntimeError("0 listings recognised (layout changed or blocked?)")
            except Exception as exc:  # noqa: BLE001
                n = self.state.errors.get(raw_url, 0) + 1
                self.state.errors[raw_url] = n
                print(f"[{sid}] ❌ {portal.label}: {exc} (consecutive failures: {n})")
                if n == ERROR_ALERT_AFTER or (n > ERROR_ALERT_AFTER and n % ERROR_REPEAT_EVERY == 0):
                    self.alert(f"⚠️ <b>SearchRadar</b>: {portal.label} for “{search.name}” "
                               f"has failed {n} runs in a row.\n<code>{str(exc)[:300]}</code>")
                continue
            if self.state.errors.pop(raw_url, 0) >= ERROR_ALERT_AFTER:
                self.alert(f"✅ <b>SearchRadar</b>: {portal.label} for “{search.name}” works again.")

            found += len(listings)
            print(f"[{sid}] {portal.label}: {len(listings)} listings on page")
            for l in listings:
                m = self.results.get(sid, l.key)
                if m is not None:  # known match still listed -> alive, track its price
                    self.price_changed(m, self.results.update_price(m, l.price))
                if self.state.is_seen(sid, l.key):
                    continue
                new += 1
                if first_run:
                    self.state.mark(sid, l.key, False)
                    continue
                if self.evaluate(topic, search, l):
                    matched += 1

        if found and sid not in self.state.initialized:
            self.state.initialized.append(sid)
        self.summary.append(f"| {topic.topic} | {search.name} | {found} | {new} | {matched} |")

    def evaluate(self, topic: Topic, search: Search, l: Listing) -> bool:
        sid, f = search.id, search.filters
        ok, why = filters.check_basic(l, f)
        if not ok:
            self.log(f"   ✗ {l.title[:60]} – {why}")
            self.state.mark(sid, l.key, False)
            return False
        missing_title = filters.missing_title_keywords(l.title, f)
        if missing_title:
            self.log(f"   ✗ {l.title[:60]} – title lacks: {', '.join(missing_title)}")
            self.state.mark(sid, l.key, False)
            return False

        text = f"{l.title} {l.text}"
        missing = filters.missing_keywords(text, f)
        need_detail = bool(missing or f.get("detail_must_not_contain"))
        if need_detail and f.get("check_details", True):
            if self.detail_budget <= 0:
                print(f"   … detail check limit reached, '{l.title[:40]}' follows next run")
                return False  # not marked -> re-evaluated next run
            self.detail_budget -= 1
            try:
                text += " " + page_text(self.fetcher.get(l.url), detect_portal(l.url).detail_selectors)
            except Exception as exc:  # noqa: BLE001
                print(f"   ! detail page failed ({exc}) – retry next run")
                return False
            bad = filters.excluded_by(text, f) or filters.detail_excluded_by(text, f)
            if bad:
                self.log(f"   ✗ {l.title[:60]} – detail page contains '{bad}'")
                self.state.mark(sid, l.key, False)
                return False
            missing = filters.missing_keywords(text, f)
        if missing:
            self.log(f"   ✗ {l.title[:60]} – missing: {', '.join(missing)}")
            self.state.mark(sid, l.key, False)
            return False

        print(f"   ✅ {l.title[:70]} – {l.url}")
        keywords = filters.found_keywords(text, f)
        self.results.add(topic.file, topic.topic, topic.emoji, sid, search.name, l, keywords)
        if self.sent >= self.notify_budget:
            print("   … notification limit reached, rest follows next run")
            return True
        msg = format_listing(topic.topic, search.name, l, keywords, topic.emoji)
        if self.tg.send(msg, thread_id=topic.telegram_thread_id, chat_id=topic.telegram_chat_id):
            self.sent += 1
            self.state.mark(sid, l.key, True)
        return True  # on send failure: not marked -> retried next run

    # ---- price changes & re-checks of stored matches ---------------------------
    def price_changed(self, m: dict, change: tuple[int, int] | None) -> None:
        if not change:
            return
        old, new = change
        print(f"   💶 price change {fmt_int(old)} → {fmt_int(new)} €: {m['title'][:50]}")
        if not self.s.get("notify_price_drops", True) or new >= old:
            return
        t = self.topics_by_file.get(m["topic_file"])
        pct = round((old - new) / old * 100) if old else 0
        import html as _h
        msg = (f"📉 <b>Price drop</b> – {_h.escape(m['search'])}\n<b>{_h.escape(m['title'])}</b>\n"
               f"<s>{fmt_int(old)} €</s> → <b>{fmt_int(new)} €</b> (−{pct} %)\n"
               f'🔗 <a href="{_h.escape(m["url"], quote=True)}">Open on {_h.escape(m["portal"])}</a>')
        if t:
            self.tg.send(msg, thread_id=t.telegram_thread_id, chat_id=t.telegram_chat_id)

    def recheck(self) -> None:
        """Visit stored matches that weren't on a result page this run: still online? price?"""
        budget = int(self.s.get("max_rechecks_per_run", 40))
        due = [m for m in self.results.due_for_check(self.run_start) if m["topic_file"] in self.topics_by_file]
        checked = removed = 0
        for m in due[:budget]:
            try:
                portal = detect_portal(m["url"])
                status, final_url, html = self.fetcher.fetch(m["url"])
                gone, price = check_detail(status, final_url, html, portal, m.get("listing_id", ""))
            except Exception as exc:  # noqa: BLE001 – blocked/network: never treat as gone
                self.log(f"   ? re-check failed for {m['title'][:40]}: {exc}")
                continue
            checked += 1
            if gone:
                if self.results.mark_gone(m):
                    removed += 1
                    print(f"   🗑 removed (no longer online): {m['title'][:60]}")
            else:
                self.price_changed(m, self.results.update_price(m, price))
        if due:
            print(f"Re-checked {checked}/{len(due)} stored matches, removed {removed}.")

    # ---- whole run --------------------------------------------------------
    def run(self, topics: list[Topic]) -> None:
        self.topics_by_file = {t.file: t for t in topics if t.enabled}
        for t in topics:
            if not t.enabled or (self.args.topic and self.args.topic not in (t.file, t.topic)):
                continue
            for s in t.searches:
                if self.args.search and self.args.search != s.name:
                    continue
                self.run_search(t, s)
        if not self.args.search and not self.args.topic:
            self.recheck()
        if not self.args.dry_run or self.args.save_state:
            self.state.save()
            self.results.save()
        md = ("| Topic | Search | Listings | New | Matches |\n|---|---|---|---|---|\n"
              + "\n".join(self.summary))
        print("\n" + md)
        if os.getenv("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
                fh.write(f"## 📡 SearchRadar\n\n{md}\n\nTelegram messages sent: {self.sent}\n")


def telegram_ids() -> int:
    """Prints chat ids and forum topic ids the bot has seen (setup helper)."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Set TELEGRAM_BOT_TOKEN first.")
        return 1
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20) as r:
        updates = json.load(r).get("result", [])
    if not updates:
        print("No updates. Write a message in each topic of your group (and disable the bot's "
              "privacy mode via @BotFather or make it admin), then run again.")
        return 0
    rows = set()
    for u in updates:
        m = u.get("message") or u.get("channel_post") or {}
        chat = m.get("chat", {})
        topic_name = (m.get("forum_topic_created") or {}).get("name") or \
            ((m.get("reply_to_message") or {}).get("forum_topic_created") or {}).get("name", "")
        rows.add((chat.get("id"), chat.get("title") or chat.get("username") or "",
                  m.get("message_thread_id"), topic_name))
    print(f"{'chat_id':>16}  {'thread_id':>9}  chat / topic")
    for chat_id, title, thread, tname in sorted(rows, key=lambda r: (str(r[0]), r[2] or 0)):
        print(f"{chat_id!s:>16}  {thread!s:>9}  {title} / {tname}")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="SearchRadar – hourly marketplace search with Telegram alerts.")
    p.add_argument("--settings", default="settings.json")
    p.add_argument("--searches", default="searches", help="directory with topic files (*.json)")
    p.add_argument("--state", default="state/seen.json")
    p.add_argument("--matches", default="state/matches.json", help="all matches (source of the web overview)")
    p.add_argument("--dry-run", action="store_true", help="don't send to Telegram, don't save state")
    p.add_argument("--save-state", action="store_true", help="save state even in dry-run")
    p.add_argument("--topic", help="only this topic (file name or topic name)")
    p.add_argument("--search", help="only this search (name)")
    p.add_argument("--test-telegram", action="store_true", help="send a test message to every topic and exit")
    p.add_argument("--telegram-ids", action="store_true", help="show chat/topic ids seen by the bot and exit")
    p.add_argument("--validate", action="store_true", help="only check the config files and exit")
    p.add_argument("-v", "--verbose", action="store_true", help="show why listings were rejected")
    args = p.parse_args()

    if args.telegram_ids:
        sys.exit(telegram_ids())

    settings = load_settings(args.settings)
    topics = load_topics(args.searches)
    if args.validate:
        for t in topics:
            print(f"✓ {t.file}: topic '{t.topic}', thread {t.telegram_thread_id}, "
                  f"{len(t.searches)} active search(es){'' if t.enabled else ' [disabled]'}")
            for s in t.searches:
                for u in s.urls:
                    detect_portal(u)
        sys.exit(0)

    active = sum(len(t.searches) for t in topics if t.enabled)
    if active == 0 and not args.test_telegram:
        print("No enabled searches – set \"enabled\": true in a file in searches/.")
        sys.exit(0)

    runner = Runner(args, settings)
    if not args.dry_run and not runner.tg.configured:
        print("❌ TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing. Add them as repository secrets "
              "or use --dry-run.")
        sys.exit(1)

    if args.test_telegram:
        ok = runner.tg.send("✅ <b>SearchRadar</b>: connection works (General / alerts).",
                            thread_id=settings.get("alerts_thread_id"))
        for t in topics:
            if t.enabled:
                ok &= runner.tg.send(f"{t.emoji} <b>SearchRadar</b>: test for topic “{t.topic}”.",
                                     thread_id=t.telegram_thread_id, chat_id=t.telegram_chat_id)
        print("Telegram OK" if ok else "Telegram ERROR – check chat id / thread ids")
        sys.exit(0 if ok else 1)

    runner.run(topics)
    sys.exit(0)
