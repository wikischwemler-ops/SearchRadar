"""Builds the web overview (site/index.html) and RESULTS.md from state/matches.json.

    python -m searchradar.site [--matches state/matches.json] [--out site] [--md RESULTS.md]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from collections import OrderedDict
from datetime import datetime, timezone

from .utils import fmt_int

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MD_PER_TOPIC = 50


def load(path: str) -> dict:
    if not os.path.exists(path):
        return {"updated": None, "matches": []}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _facts(m: dict) -> str:
    parts = []
    if m.get("mileage") is not None:
        parts.append(f"{fmt_int(m['mileage'])} km")
    if m.get("year"):
        parts.append(str(m["year"]))
    if m.get("location"):
        parts.append(m["location"])
    return " · ".join(parts)


def _md_cell(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ")


def build_markdown(data: dict) -> str:
    matches = data["matches"]
    by_topic: "OrderedDict[str, list]" = OrderedDict()
    for m in matches:
        by_topic.setdefault(f"{m.get('emoji', '')} {m['topic']}".strip(), []).append(m)
    out = ['<p align="center"><img src="assets/logo.svg" width="80" alt=""></p>\n',
           "# SearchRadar – results\n",
           f"Updated: {data.get('updated') or '–'} (UTC) · {len(matches)} active listings\n"]
    if not matches:
        out.append("\n_No matches yet._\n")
    for topic, items in by_topic.items():
        out.append(f"\n## {topic} ({len(items)})\n")
        out.append("| Found | Listing | Price | Details | Search | Portal |\n|---|---|---:|---|---|---|")
        for m in items[:MD_PER_TOPIC]:
            price = f"{fmt_int(m['price'])} €" if m.get("price") is not None else "–"
            hist = [h[1] for h in m.get("history", []) if h[1] is not None]
            if len(hist) > 1 and hist[0] != m.get("price"):
                arrow = "▼" if m["price"] < hist[0] else "▲"
                price += f" {arrow} (was {fmt_int(hist[0])} €)"
            out.append(f"| {m['found'][:16].replace('T', ' ')} | [{_md_cell(m['title'] or 'Listing')}]({m['url']}) "
                       f"| {price} | {_md_cell(_facts(m))} | {_md_cell(m['search'])} | {m['portal']} |")
        if len(items) > MD_PER_TOPIC:
            out.append(f"\n_… {len(items) - MD_PER_TOPIC} older matches on the web overview._")
    return "\n".join(out) + "\n"


def build_html(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", payload)


def main() -> None:
    p = argparse.ArgumentParser(description="Build the SearchRadar web overview.")
    p.add_argument("--matches", default="state/matches.json")
    p.add_argument("--out", default="site")
    p.add_argument("--md", default="RESULTS.md")
    a = p.parse_args()
    data = load(a.matches)
    data.setdefault("updated", None)
    data["built"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(build_html(data))
    for name in ("logo.svg", "logo.png"):
        src = os.path.join(ROOT, "assets", name)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(a.out, name))
    with open(os.path.join(a.out, ".nojekyll"), "w") as fh:
        fh.write("")
    if a.md:
        with open(a.md, "w", encoding="utf-8") as fh:
            fh.write(build_markdown(data))
    print(f"Built {a.out}/index.html and {a.md} with {len(data['matches'])} matches.")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>SearchRadar – results</title>
<link rel="icon" href="logo.svg" type="image/svg+xml">
<style>
  :root {
    --bg: #071a2c; --bg2: #0b2740; --card: #0f2f4b; --card-hi: #133a5c;
    --line: rgba(56,189,248,.18); --text: #e6f4ff; --muted: #8fb3cc;
    --cyan: #38bdf8; --teal: #2dd4bf; --new: #facc15;
    --r: 14px;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; }
  body {
    font: 15px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    color: var(--text);
    background: radial-gradient(1200px 600px at 80% -10%, #0e3a5c 0%, transparent 60%), var(--bg);
    min-height: 100vh;
  }
  header {
    position: sticky; top: 0; z-index: 5;
    background: rgba(7,26,44,.88); backdrop-filter: blur(10px);
    border-bottom: 1px solid var(--line);
  }
  .wrap { max-width: 1180px; margin: 0 auto; padding: 0 16px; }
  .brand { display: flex; align-items: center; gap: 12px; padding: 14px 0 10px; }
  .brand img { width: 40px; height: 40px; }
  .brand h1 { font-size: 20px; margin: 0; letter-spacing: .2px; }
  .brand h1 span { color: var(--teal); }
  .brand .upd { margin-left: auto; color: var(--muted); font-size: 12.5px; text-align: right; }
  .controls { display: flex; flex-wrap: wrap; gap: 8px; padding-bottom: 12px; align-items: center; }
  .chips { display: flex; gap: 6px; overflow-x: auto; scrollbar-width: none; flex: 1 1 100%; padding-bottom: 2px; }
  .chip {
    flex: none; border: 1px solid var(--line); background: var(--bg2); color: var(--text);
    padding: 6px 12px; border-radius: 999px; font: inherit; font-size: 13.5px; cursor: pointer;
  }
  .chip b { color: var(--muted); font-weight: 500; margin-left: 4px; }
  .chip[aria-pressed="true"] { background: linear-gradient(135deg, var(--teal), var(--cyan)); color: #04202f; border-color: transparent; }
  .chip[aria-pressed="true"] b { color: #04202f; }
  input[type=search], select {
    background: var(--bg2); color: var(--text); border: 1px solid var(--line);
    border-radius: 10px; padding: 8px 12px; font: inherit; font-size: 14px;
  }
  input[type=search] { flex: 1 1 220px; min-width: 0; }
  label.only-new { display: flex; gap: 6px; align-items: center; color: var(--muted); font-size: 13.5px; }
  main { padding: 18px 0 40px; }
  .stats { color: var(--muted); font-size: 13px; margin: 0 0 12px; }
  .grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); }
  .card {
    background: linear-gradient(180deg, var(--card), var(--bg2));
    border: 1px solid var(--line); border-radius: var(--r);
    padding: 14px 14px 12px; display: flex; flex-direction: column; gap: 8px;
    transition: border-color .15s, transform .15s;
  }
  .card:hover { border-color: rgba(45,212,191,.55); transform: translateY(-1px); }
  .meta { display: flex; gap: 8px; align-items: center; font-size: 12.5px; color: var(--muted); }
  .meta .search { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .badge-new { background: var(--new); color: #2a2200; font-weight: 700; font-size: 11px; padding: 1px 7px; border-radius: 999px; }
  .title { font-size: 15.5px; font-weight: 600; margin: 0; }
  .title a { color: var(--text); text-decoration: none; }
  .title a:hover { color: var(--teal); }
  .price { font-size: 20px; font-weight: 700; color: var(--teal); }
  .facts { color: var(--muted); font-size: 13.5px; }
  .kw { display: flex; flex-wrap: wrap; gap: 5px; }
  .kw span { font-size: 12px; padding: 2px 8px; border-radius: 999px; background: rgba(45,212,191,.12); color: var(--teal); border: 1px solid rgba(45,212,191,.25); }
  .foot { margin-top: auto; display: flex; align-items: center; gap: 8px; padding-top: 6px; border-top: 1px dashed var(--line); font-size: 12.5px; color: var(--muted); }
  .portal { padding: 2px 8px; border-radius: 6px; background: rgba(56,189,248,.12); color: var(--cyan); }
  .open {
    margin-left: auto; text-decoration: none; font-weight: 600; font-size: 13px;
    color: #04202f; background: linear-gradient(135deg, var(--teal), var(--cyan));
    padding: 6px 12px; border-radius: 8px;
  }
  .pricerow { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
  .delta { font-size: 13px; font-weight: 600; padding: 1px 8px; border-radius: 999px; }
  .delta.down { color: #4ade80; background: rgba(74,222,128,.12); }
  .delta.up { color: #f87171; background: rgba(248,113,113,.12); }
  .was { color: var(--muted); text-decoration: line-through; font-size: 13px; }
  .chart { width: 100%; height: 64px; display: block; }
  .chart .axis { fill: var(--muted); font-size: 10px; }
  .charthead { display: flex; justify-content: space-between; font-size: 11.5px; color: var(--muted); margin-bottom: 2px; }
  .empty { text-align: center; padding: 60px 16px; color: var(--muted); }
  .empty img { width: 90px; opacity: .8; }
  footer { margin-top: -12px; color: var(--muted); font-size: 12px; text-align: center; padding: 0 0 28px; }
  @media (max-width: 520px) {
    .brand .upd { font-size: 11.5px; }
    .grid { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
<header>
  <div class="wrap">
    <div class="brand">
      <img src="logo.svg" alt="">
      <h1>Search<span>Radar</span></h1>
      <div class="upd" id="upd"></div>
    </div>
    <div class="controls">
      <div class="chips" id="chips" role="toolbar" aria-label="Topics"></div>
      <input type="search" id="q" placeholder="Filter: title, place, keyword…" aria-label="Filter">
      <select id="sort" aria-label="Sort">
        <option value="new">Newest first</option>
        <option value="price-asc">Price ↑</option>
        <option value="price-desc">Price ↓</option>
      </select>
      <label class="only-new"><input type="checkbox" id="onlyNew"> last 24 h</label>
    </div>
  </div>
</header>
<main class="wrap">
  <p class="stats" id="stats"></p>
  <div class="grid" id="grid"></div>
</main>
<footer>Only listings that are still online · price checked every hour · built by GitHub Actions</footer>

<script id="data" type="application/json">__DATA__</script>
<script>
(() => {
  const data = JSON.parse(document.getElementById("data").textContent);
  const all = data.matches || [];
  const $ = id => document.getElementById(id);
  const store = {
    get(k, d) { try { return localStorage.getItem("sr." + k) ?? d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem("sr." + k, v); } catch {} }
  };
  const nf = new Intl.NumberFormat("de-DE");
  const DAY = 864e5;
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const ago = iso => {
    const d = (Date.now() - new Date(iso)) / 1000;
    if (d < 3600) return Math.max(1, Math.round(d / 60)) + " min ago";
    if (d < 86400) return Math.round(d / 3600) + " h ago";
    return Math.round(d / 86400) + " d ago";
  };

  let topic = store.get("topic", "all");
  const topics = [];
  for (const m of all) if (!topics.some(t => t.file === m.topic_file))
    topics.push({file: m.topic_file, name: m.topic, emoji: m.emoji || ""});
  if (topic !== "all" && !topics.some(t => t.file === topic)) topic = "all";
  $("sort").value = store.get("sort", "new");

  $("upd").innerHTML = data.updated
    ? "Updated<br>" + esc(new Date(data.updated).toLocaleString("de-DE", {dateStyle: "medium", timeStyle: "short"}))
    : "No run yet";

  function hist(m) {
    return (m.history || []).filter(h => h[1] != null).map(h => [new Date(h[0]).getTime(), h[1]]);
  }

  function priceBlock(m) {
    if (m.price == null) return "";
    const h = hist(m);
    let extra = "";
    if (h.length > 1 && h[0][1] !== m.price) {
      const first = h[0][1], diff = m.price - first, pct = Math.round(diff / first * 100);
      extra = `<span class="was">${nf.format(first)} €</span>
        <span class="delta ${diff < 0 ? "down" : "up"}">${diff < 0 ? "▼" : "▲"} ${nf.format(Math.abs(diff))} € (${pct > 0 ? "+" : ""}${pct} %)</span>`;
    }
    return `<div class="pricerow"><span class="price">${nf.format(m.price)} €</span>${extra}</div>`;
  }

  // step-line chart of the price history, extended to the last check
  function chart(m) {
    const h = hist(m);
    if (!h.length) return "";
    const end = Math.max(new Date(m.last_checked || m.found).getTime(), h[h.length - 1][0]);
    const pts = h.concat([[end, h[h.length - 1][1]]]);
    const W = 300, H = 64, P = 4, L = 34;
    const t0 = pts[0][0], t1 = Math.max(pts[pts.length - 1][0], t0 + 1);
    const prices = pts.map(p => p[1]);
    let lo = Math.min(...prices), hi = Math.max(...prices);
    const flat = lo === hi;
    if (flat) { lo -= Math.max(1, lo * 0.05); hi += Math.max(1, hi * 0.05); }
    const x = t => L + (t - t0) / (t1 - t0) * (W - L - P);
    const y = v => P + (hi - v) / (hi - lo) * (H - 2 * P - 10);
    let d = `M${x(pts[0][0]).toFixed(1)},${y(pts[0][1]).toFixed(1)}`;
    for (let i = 1; i < pts.length; i++)
      d += ` H${x(pts[i][0]).toFixed(1)} V${y(pts[i][1]).toFixed(1)}`;
    const area = d + ` V${H - 10} H${x(pts[0][0]).toFixed(1)} Z`;
    const dots = h.map(p => `<circle cx="${x(p[0]).toFixed(1)}" cy="${y(p[1]).toFixed(1)}" r="2.6" fill="var(--teal)">
        <title>${new Date(p[0]).toLocaleString("de-DE", {dateStyle: "short", timeStyle: "short"})}: ${nf.format(p[1])} €</title></circle>`).join("");
    const days = Math.max(0, Math.round((t1 - t0) / DAY));
    const k = v => v >= 10000 ? nf.format(Math.round(v / 100) / 10) + "k" : nf.format(Math.round(v));
    return `<div><div class="charthead"><span>Price history</span><span>${h.length > 1 ? (h.length - 1) + " price change" + (h.length > 2 ? "s" : "") : "price stable"} · ${days} d</span></div>
      <svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Price history">
        <line x1="${L}" x2="${W - P}" y1="${H - 10}" y2="${H - 10}" stroke="var(--line)"/>
        ${flat ? `<text class="axis" x="0" y="${y(prices[0]) + 4}">${k(prices[0])}</text>`
               : `<text class="axis" x="0" y="${y(hi) + 4}">${k(hi)}</text><text class="axis" x="0" y="${y(lo) + 4}">${k(lo)}</text>`}
        <path d="${area}" fill="rgba(45,212,191,.10)"/>
        <path d="${d}" fill="none" stroke="var(--teal)" stroke-width="2" vector-effect="non-scaling-stroke"/>
        ${dots}
      </svg></div>`;
  }

  function chips() {
    const btn = (key, label, n) =>
      `<button class="chip" data-t="${esc(key)}" aria-pressed="${topic === key}">${label}<b>${n}</b></button>`;
    $("chips").innerHTML = btn("all", "All", all.length) +
      topics.map(t => btn(t.file, esc(t.emoji + " " + t.name), all.filter(m => m.topic_file === t.file).length)).join("");
  }

  function render() {
    const q = $("q").value.trim().toLowerCase();
    const onlyNew = $("onlyNew").checked;
    const sort = $("sort").value;
    let list = all.filter(m =>
      (topic === "all" || m.topic_file === topic) &&
      (!onlyNew || Date.now() - new Date(m.found) < DAY) &&
      (!q || [m.title, m.location, m.search, m.portal, ...(m.keywords || [])].join(" ").toLowerCase().includes(q)));
    if (sort !== "new") {
      const dir = sort === "price-asc" ? 1 : -1;
      list = list.slice().sort((a, b) => {
        if (a.price == null) return b.price == null ? 0 : 1;   // listings without price last
        if (b.price == null) return -1;
        return dir * (a.price - b.price);
      });
    }
    $("stats").textContent = `${list.length} of ${all.length} matches`;
    if (!list.length) {
      $("grid").innerHTML = `<div class="empty" style="grid-column:1/-1"><img src="logo.svg" alt=""><p>${
        all.length ? "Nothing matches this filter." : "No matches yet – the radar is still scanning."}</p></div>`;
      return;
    }
    $("grid").innerHTML = list.map(m => {
      const fresh = Date.now() - new Date(m.found) < DAY;
      const facts = [m.mileage != null ? nf.format(m.mileage) + " km" : "", m.year || "", m.location || ""].filter(Boolean).join(" · ");
      return `<article class="card">
        <div class="meta">${fresh ? '<span class="badge-new">NEW</span>' : ""}<span>${esc(m.emoji || "")}</span><span class="search">${esc(m.search)}</span></div>
        <h2 class="title"><a href="${esc(m.url)}" target="_blank" rel="noopener noreferrer">${esc(m.title || "Listing")}</a></h2>
        ${priceBlock(m)}
        ${chart(m)}
        ${facts ? `<div class="facts">${esc(facts)}</div>` : ""}
        ${(m.keywords || []).length ? `<div class="kw">${m.keywords.map(k => `<span>${esc(k)}</span>`).join("")}</div>` : ""}
        <div class="foot"><span class="portal">${esc(m.portal)}</span><span title="found ${esc(m.found)} · last checked ${esc(m.last_checked || m.found)}">found ${ago(m.found)}</span>
          <a class="open" href="${esc(m.url)}" target="_blank" rel="noopener noreferrer">Open ↗</a></div>
      </article>`;
    }).join("");
  }

  $("chips").addEventListener("click", e => {
    const b = e.target.closest(".chip"); if (!b) return;
    topic = b.dataset.t; store.set("topic", topic); chips(); render();
  });
  $("q").addEventListener("input", render);
  $("onlyNew").addEventListener("change", render);
  $("sort").addEventListener("change", () => { store.set("sort", $("sort").value); render(); });
  chips(); render();
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
