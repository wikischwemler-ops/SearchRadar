# SearchRadar

Hourly marketplace search (AutoScout24, mobile.de, Kleinanzeigen) with Telegram forum-topic alerts, run by GitHub Actions.

- Read `.claude/skills/searchradar/SKILL.md` before adding searches, filters, Telegram topics or portals.
- Code, docs and messages are in English; filter keywords use the listings' language (German).
- Before committing: `python -m searchradar --validate && python -m pytest -q`.
- `state/seen.json` is written by the workflow – don't edit it by hand except to reset a search.
- Never commit Telegram tokens; they live in the repo secrets `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
