---
name: searchradar
description: Work on the SearchRadar repo - add or change a search topic in searches/*.json, write realistic minimum criteria, map a topic to a Telegram forum thread, add a new marketplace portal, or debug a failing run.
---

# SearchRadar

SearchRadar checks marketplace search URLs (AutoScout24, mobile.de, Kleinanzeigen) every hour via
GitHub Actions and sends a Telegram message only for listings that pass **all** minimum criteria.
Everything in the repo (code, docs, messages) is in **English**; keywords inside filters are written in
the language of the listings (German for German portals).

## Layout

| Path | Purpose |
|---|---|
| `settings.json` | global limits, `alerts_thread_id` |
| `searches/<topic>.json` | one file per topic (cars, bikes, monitors, …) |
| `searchradar/portals/` | one parser per portal + registry in `__init__.py` |
| `searchradar/filters.py` | minimum-criteria logic |
| `searchradar/main.py` | run loop, CLI |
| `state/seen.json` | handled listings, committed back by the workflow – never edit by hand except to reset |
| `.github/workflows/searchradar.yml` | hourly schedule (minute 17, UTC) |

## 1. Add a new search topic

1. Ask the user for: what they look for, must-have properties, deal-breakers, price range, postcode + radius,
   which portals. Ask for the Telegram `thread_id` of the topic or leave `null` and tell them how to get it
   (`python -m searchradar --telegram-ids`).
2. Copy an existing file in `searches/` to `searches/<topic>.json` (lowercase English file name, plural: `laptops.json`).
3. Fill `topic`, `emoji`, `telegram_thread_id`, `defaults`, `searches[]`.
4. Search URLs: the user creates them on the portal (filters, postcode, radius, **sort newest first**) and pastes them.
   Never invent query parameters you are unsure about – a wrong parameter silently widens the search.
   Placeholder postcodes are fine only together with `"enabled": false`.
5. Run `python -m searchradar --validate` and `python -m pytest -q`.

## 2. Write realistic minimum criteria

The goal is few, precise alerts. A good filter set:

- **`min_price` always** – removes "price on request", parts, scams, wanted ads with 1 €.
- **`max_price`** a bit above the target price (people negotiate, "VB").
- **`title_must_contain`** for the defining property (model, size class) – cheapest and most precise check.
- **`must_contain`** for equipment/specs; group synonyms and abbreviations as one list entry:
  `["AHK", "Anhängerkupplung"]`, `["4K", "UHD", "3840"]`, `["RH 56", "56 cm", "Größe M"]`.
- **`must_not_contain`** red flags: `Unfall`, `defekt`, `Bastler`, `Export`, `Motorschaden`, on Kleinanzeigen also `Suche`, `Gesuch`, `Tausch`.
- **`require_known: ["price"]`** (+ `mileage`/`year` for vehicles) when unknown values should not pass.
- Vehicles: `max_mileage`, `min_year`. Non-vehicles: don't use mileage/year filters.

Matching is case-insensitive and anchored at the **start of a word** (`Pano` → *Panoramadach*; `suche` ✗ *versuche*).
Avoid bare numbers like `"27"` or `"56"` – they also match prices (`270 €`, `560 €`). Write `"27 Zoll"`, `"RH 56"`.

Put shared rules in the file's `defaults`; per-search `filters` override keys from `defaults` (no list merging).

## 3. Telegram topics

- One bot, one group with **Topics** enabled, one topic per search file.
- `TELEGRAM_CHAT_ID` secret = group id (`-100…`); per file `telegram_thread_id` = topic id.
- Optional per-file `telegram_chat_id` to send a topic to another chat.
- Warnings (portal failed 3× in a row, recovered) go to `settings.json → alerts_thread_id`.
- Test: workflow *Run workflow* with "Send Telegram test message", or `python -m searchradar --test-telegram`.

## 4. Add a new portal

1. Get a saved HTML sample of a result page from the user (or `curl` one) – put a trimmed version in a test.
2. Create `searchradar/portals/<key>.py`:
   ```python
   from bs4 import BeautifulSoup
   from ..models import Listing
   from ..utils import clean, find_price, to_int

   NAME = "<key>"

   def parse(html: str) -> list[Listing]:
       soup = BeautifulSoup(html, "html.parser")
       out = []
       for card in soup.select("<card selector>"):
           ...  # id, absolute url, title, price, location, text=clean(card.get_text(" "))
       return out
   ```
   Rules: stable unique `id` per listing, absolute `url`, `text` = whole card text, dedupe ids, never raise on a
   single broken card. Prefer data attributes or embedded JSON over CSS class names.
3. Register in `searchradar/portals/__init__.py → PORTALS` with `label`, `domain` and, if the portal supports it,
   the newest-first sort parameter.
4. Add tests in `tests/` (parse result, numbers, `detect_portal`). Run `python -m pytest -q`.
5. Mention the portal in the README table.

## 5. Debug a run

- GitHub → Actions → run → step *Search* shows per-search counts and, with `-v`, why listings were rejected.
- `0 listings recognised` → layout changed or block page; save the HTML and fix the parser.
- `HTTP 403/429` or captcha → bot protection (typical for mobile.de on GitHub runners); not fixable by retries.
- Locally: `python -m searchradar --dry-run -v --topic <file>`.
- Re-evaluate old listings after changing filters: rename the search or remove its keys from `state/seen.json`.

## Conventions

- Python 3.12, only `beautifulsoup4`, `curl_cffi`, `requests`.
- Keep requests polite: first page only, random delays, detail pages only for listings that passed the cheap checks.
- Don't commit secrets; tokens live only in GitHub secrets.
