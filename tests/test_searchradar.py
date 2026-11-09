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
