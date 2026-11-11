"""Tests with small, simplified result pages. Run: python -m pytest -q"""
import json
import os

from searchradar import filters
from searchradar.config import load_settings, load_topics
from searchradar.portals import PORTALS, autoscout24, detect_portal, kleinanzeigen, mobile_de, newest_first

ROOT = os.path.dirname(os.path.dirname(__file__))

AS24 = """
<main>
 <article data-guid="abc-123" data-make="volkswagen" data-model="golf" data-price="32990"
          data-mileage="45000" data-first-registration="03-2021" data-listing-zip-code="10115">
   <a href="/angebote/volkswagen-golf-gti-abc-123"><h2>VW Golf GTI 2.0 TSI DSG</h2></a>
   <span>Panorama, AHK</span>
 </article>
</main>"""

AS24_NEXT = json.dumps({"props": {"pageProps": {"listings": [{
    "id": "xyz-9", "url": "/angebote/xyz-9",
    "vehicle": {"make": "VW", "model": "Golf", "modelVersionInput": "GTI DSG"},
    "tracking": {"price": "31000", "mileage": "50000", "firstRegistration": "05-2020"},
    "location": {"zip": "10115", "city": "Berlin"}}]}}})

KA_CAR = """
<ul>
 <li><article class="aditem" data-adid="2711" data-href="/s-anzeige/vw-golf-gti/2711-216-3331">
   <div class="aditem-main--top--left">10115 Berlin</div>
   <h2><a class="ellipsis" href="/s-anzeige/vw-golf-gti/2711-216-3331">VW Golf 8 GTI DSG Pano</a></h2>
   <p class="aditem-main--middle--description">Scheckheft, AHK, Nichtraucher</p>
   <p class="aditem-main--middle--price-shipping--price">29.900 € VB</p>
   <div class="aditem-main--bottom"><span class="simpletag">62.000 km</span><span class="simpletag">EZ 07/2020</span></div>
 </article></li>
</ul>"""

KA_BIKE = """
<article class="aditem" data-adid="555" data-href="/s-anzeige/rennrad/555-217-3331">
  <div class="aditem-main--top--left">10117 Berlin</div>
  <h2><a class="ellipsis" href="/s-anzeige/rennrad/555-217-3331">Canyon Rennrad Carbon Ultegra</a></h2>
  <p class="aditem-main--middle--description">RH 56, top Zustand</p>
  <p class="aditem-main--middle--price-shipping--price">1.450 € VB</p>
  <div class="aditem-main--bottom"><span class="simpletag">Versand möglich</span></div>
</article>"""

MOBILE = """
<div><a href="/fahrzeuge/details.html?id=987654&amp;foo=1">
  <h2>Volkswagen Golf GTI DSG</h2><span>EZ 02/2021 · 38.500 km · 33.450 €</span></a></div>"""


def test_autoscout24_articles():
    (l,) = autoscout24.parse(AS24)
    assert (l.id, l.price, l.mileage, l.year) == ("abc-123", 32990, 45000, 2021)
    assert l.url.endswith("/angebote/volkswagen-golf-gti-abc-123")


def test_autoscout24_next_data_fallback():
    (l,) = autoscout24.parse(f'<script id="__NEXT_DATA__" type="application/json">{AS24_NEXT}</script>')
    assert (l.id, l.price, l.mileage, l.year) == ("xyz-9", 31000, 50000, 2020)


def test_kleinanzeigen_car_and_bike():
    (car,) = kleinanzeigen.parse(KA_CAR)
    assert (car.id, car.price, car.mileage, car.year, car.location) == ("2711", 29900, 62000, 2020, "10115 Berlin")
    (bike,) = kleinanzeigen.parse(KA_BIKE)
    assert (bike.id, bike.price, bike.mileage, bike.year) == ("555", 1450, None, None)


def test_mobile_de():
    (l,) = mobile_de.parse(MOBILE)
    assert (l.id, l.price, l.mileage, l.year) == ("987654", 33450, 38500, 2021)


def test_filters():
    (l,) = kleinanzeigen.parse(KA_CAR)
    f = {"max_price": 30000, "title_must_contain": ["GTI"],
         "must_contain": ["DSG", ["Panorama", "Pano"], "AHK"], "must_not_contain": ["Unfall"]}
    assert filters.check_basic(l, f)[0]
    assert filters.missing_title_keywords(l.title, f) == []
    assert filters.missing_keywords(f"{l.title} {l.text}", f) == []
    assert filters.missing_keywords("Golf GTI", f) == ["DSG", "Panorama / Pano", "AHK"]
    assert not filters.check_basic(l, {"max_price": 20000})[0]
    assert not filters.check_basic(l, {"min_year": 2021})[0]
    assert not filters.check_basic(l, {"require_known": ["year", "price", "location", "mileage"], "max_year": 2019})[0]


def test_word_start_matching():
    t = filters._norm("Ich versuche es mit Panoramadach")
    assert filters.has(t, "pano") and not filters.has(t, "suche")
    (bike,) = kleinanzeigen.parse(KA_BIKE)
    assert not filters.check_basic(bike, {"require_known": ["mileage"]})[0]  # unknown -> rejected


def test_portals():
    assert detect_portal("https://www.autoscout24.de/lst/vw").key == "autoscout24"
    assert detect_portal("https://suchen.mobile.de/fahrzeuge/search.html").key == "mobile_de"
    assert detect_portal("https://www.kleinanzeigen.de/s-fahrraeder/k0c217").key == "kleinanzeigen"
    assert "sort=age" in newest_first("https://www.autoscout24.de/lst/vw?zip=1", PORTALS["autoscout24"])
    url = "https://www.kleinanzeigen.de/s-autos/k0c216"
    assert newest_first(url, PORTALS["kleinanzeigen"]) == url


def test_shipped_config_is_valid():
    s = load_settings(os.path.join(ROOT, "settings.json"))
    assert s["max_notifications_per_run"] > 0
    topics = load_topics(os.path.join(ROOT, "searches"))
    assert {t.file for t in topics} >= {"cars", "bikes", "monitors"}
    for t in topics:
        for search in t.searches:
            assert search.filters.get("must_not_contain"), "defaults must be merged into filters"
            for u in search.urls:
                detect_portal(u)


def test_regex_terms_for_clothing_size():
    topics = {t.file: t for t in load_topics(os.path.join(ROOT, "searches"))}
    f = topics["clothing"].searches[0].filters
    for text in ["Adidas Terrex Jacke Größe S", "Terrex Hose Gr. S", "Terrex Softshell S/M", "size small"]:
        assert filters.missing_keywords(text, f) == [], text
    for text in ["Terrex Jacke Größe XS", "Terrex Größe Schwarz M", "Terrex Jacke Gr. M", "Terrex Größe S-M"]:
        assert filters.missing_keywords(text, f) != [], text
    assert filters.found_keywords("Terrex Jacke Größe S", f) == ["größe s"]
    assert filters.excluded_by("Adidas Terrex Kinderjacke Größe S", f) == "Kinder"


# ---- re-checks, price history, overview ------------------------------------------------

from searchradar.portals import check_detail
from searchradar.results import Results
from searchradar import site


def test_check_detail_gone_and_price():
    ka = PORTALS["kleinanzeigen"]
    alive = ('<h1 id="viewad-title">Adidas Terrex Jacke Größe S</h1><h2 id="viewad-price">55 € VB</h2>'
             '<p id="viewad-description-text">Originalkarton nicht mehr verfügbar.</p>'
             '<section class="similar">Andere Anzeige wurde gelöscht</section>')
    url = "https://www.kleinanzeigen.de/s-anzeige/x/777-160-1"
    assert check_detail(200, url, alive, ka, "777") == (False, 55)          # description text must not count
    sold = alive.replace("Adidas Terrex", "Gelöscht • Adidas Terrex")
    assert check_detail(200, url, sold, ka, "777")[0] is True
    assert check_detail(404, url, "", ka, "777")[0] is True
    assert check_detail(200, "https://www.kleinanzeigen.de/s-terrex/k0", "<p>Suche</p>", ka, "777")[0] is True
    gone_page = "<h1>Ups</h1><p>Die Anzeige ist nicht mehr verfügbar.</p>"
    assert check_detail(200, url, gone_page, ka, "777")[0] is True
    ld = '<script type="application/ld+json">{"@type":"Car","offers":{"price":"31490.00"}}</script><h1>x</h1>'
    assert check_detail(200, "https://www.autoscout24.de/angebote/abc-123", ld, PORTALS["autoscout24"], "abc-123") == (False, 31490)


def test_results_history_and_removal(tmp_path):
    (l,) = kleinanzeigen.parse(KA_CAR)
    r = Results(str(tmp_path / "m.json"))
    r.add("cars", "Cars", "🚗", "cars/Golf", "Golf", l, ["DSG"])
    m = r.get("cars/Golf", l.key)
    assert m["history"] == [[m["found"], 29900]]
    assert r.update_price(m, 29900) is None
    assert r.update_price(m, 28500) == (29900, 28500) and len(m["history"]) == 2
    assert r.mark_gone(m) is False            # first "gone" may be a hiccup
    r.update_price(m, None)                   # seen again -> counter reset
    assert m["gone_count"] == 0
    assert r.mark_gone(m) is False and r.mark_gone(m) is True
    assert r.get("cars/Golf", l.key) is None
    r.save()
    assert json.load(open(tmp_path / "m.json"))["matches"] == []


def test_site_build(tmp_path):
    (l,) = kleinanzeigen.parse(KA_CAR)
    r = Results(str(tmp_path / "m.json"))
    r.add("cars", "Cars", "🚗", "cars/Golf", "Golf", l, ["DSG"])
    r.update_price(r.get("cars/Golf", l.key), 27900)
    r.save()
    data = site.load(str(tmp_path / "m.json"))
    html = site.build_html(data)
    assert "VW Golf 8 GTI DSG Pano" in html and "</script><" not in html.split('id="data"')[1].split("</script>")[0]
    md = site.build_markdown(data)
    assert "27.900 € ▼ (was 29.900 €)" in md and "(https://www.kleinanzeigen.de/s-anzeige/" in md


# ---- real HTML samples (Nov 2026) and the Golf 7 search ----------------------------------

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return fh.read()


def test_kleinanzeigen_new_layout():
    parsed = kleinanzeigen.parse(_fixture("kleinanzeigen.html"))
    assert [l.id for l in parsed] == ["3562284248", "3554963525", "3521667313"]   # no nationwide "altads"
    golf, facelift, wanted = parsed
    assert (golf.id, golf.title, golf.price, golf.mileage, golf.year, golf.location) == \
        ("3562284248", "VW Golf 7 1.2 TSI", 9490, 90000, 2016, "73061 Ebersbach an der Fils")
    assert golf.url == "https://www.kleinanzeigen.de/s-anzeige/vw-golf-7-1-2-tsi/3562284248-216-8871"
    assert (facelift.price, facelift.mileage, facelift.year) == (7100, 142300, 2018)  # not the struck-through 7.300
    assert wanted.extra["wanted"] is True


def test_mobile_de_current_layout():
    sportsvan, golf = mobile_de.parse(_fixture("mobile_de.html"))
    assert (golf.id, golf.title, golf.price, golf.mileage, golf.year, golf.location) == \
        ("446694686", "Volkswagen Golf VII Lim. Trendline BMT/Start-Stopp- I Hand", 8999, 147000, 2018, "70469 Stuttgart")
    assert golf.url == "https://suchen.mobile.de/fahrzeuge/details.html?id=446694686"
    assert sportsvan.title.startswith("Volkswagen Golf Sportsvan")   # "Gesponsert" badge stripped


def test_golf7_search_criteria():
    topics = {t.file: t for t in load_topics(os.path.join(ROOT, "searches"))}
    f = topics["cars"].searches[0].filters
    assert "Gesuch" in f["must_not_contain"] and "Variant" in f["must_not_contain"]   # lists merged
    golf, facelift, wanted = kleinanzeigen.parse(_fixture("kleinanzeigen.html"))
    sportsvan, golf_mobile = mobile_de.parse(_fixture("mobile_de.html"))

    def ok(l):
        return filters.check_basic(l, f)[0] and not filters.missing_title_keywords(l.title, f)

    assert ok(golf) and ok(facelift) and ok(golf_mobile)           # "Unfallfrei" must not reject
    assert not ok(wanted) and not ok(sportsvan)
    for title in ["VW Golf 6 1.4", "Golf VI Comfortline", "Golf 8 Life", "Golf VIII", "VW Golf 4", "Golf Variant 1.0"]:
        assert filters.excluded_by(title, f), title
    for title in ["Golf VII Highline", "Golf 7.5 TSI", "VW Golf 7 1.0 TSI", "Golf 1.2 TSI BlueMotion"]:
        assert not filters.excluded_by(title, f), title
    assert filters.excluded_by("Golf 7 Unfallwagen", f) and not filters.excluded_by("Golf 7 unfallfrei", f)
    assert filters.excluded_by("Motor defekt", f) and not filters.excluded_by("keine Defekte", f)
