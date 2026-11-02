"""Place names to coordinates, without a geocoding service.

The gazetteer (data/places.json, built by scripts/build_places.py) holds every
Spanish municipality with a fuel station and the average position of its
stations. That covers what people ask about — towns and cities — and anything
finer (a street, a landmark) the calling model passes as lat/lng.
"""

import difflib
import json
import re
import unicodedata
from dataclasses import dataclass
from functools import cache
from importlib import resources


@dataclass(frozen=True)
class Municipality:
    slug: str
    name: str
    province_slug: str
    province_name: str
    lat: float
    lng: float
    station_count: int

    @property
    def label(self) -> str:
        return self.name if self.name == self.province_name else f"{self.name} ({self.province_name})"


@dataclass(frozen=True)
class Province:
    slug: str
    name: str
    lat: float
    lng: float
    station_count: int


# Names people use that the gazetteer spells another way: exonyms, the other
# official language, or the short form of a city's name.
MUNICIPALITY_ALIASES: dict[str, str] = {
    "palma": "palma-de-mallorca",
    "san sebastian": "donostia-san-sebastian",
    "donostia": "donostia-san-sebastian",
    "vitoria": "vitoria-gasteiz",
    "gasteiz": "vitoria-gasteiz",
    "la coruna": "a-coruna",
    "corunna": "a-coruna",
    "ibiza": "eivissa",
    "mao": "mahon",
    "gerona": "girona",
    "lerida": "lleida",
    "orense": "ourense",
    "las palmas": "las-palmas-de-gran-canaria",
    "seville": "sevilla",
    "saragossa": "zaragoza",
    "xixon": "gijon",
    "iruna": "pamplona-iruna",
    "bilbo": "bilbao",
}

PROVINCE_ALIASES: dict[str, str] = {
    "valencia": "valencia-valencia",
    "castellon": "castellon-castello",
    "castello": "castellon-castello",
    "alava": "araba-alava",
    "araba": "araba-alava",
    "vizcaya": "bizkaia",
    "biscay": "bizkaia",
    "guipuzcoa": "gipuzkoa",
    "baleares": "illes-balears",
    "islas baleares": "illes-balears",
    "balearic islands": "illes-balears",
    "mallorca": "illes-balears",
    "majorca": "illes-balears",
    "la coruna": "a-coruna",
    "coruna": "a-coruna",
    "gerona": "girona",
    "lerida": "lleida",
    "orense": "ourense",
    "tenerife": "santa-cruz-de-tenerife",
    "gran canaria": "las-palmas",
    "navarre": "navarra",
    "seville": "sevilla",
    "saragossa": "zaragoza",
    "rioja": "la-rioja",
}

_SPAIN = {"spain", "espana", "es"}


def normalize(text: str) -> str:
    """Lowercase, no accents, no punctuation: 'Cádiz, España' -> 'cadiz espana'."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return text.strip()


class Gazetteer:
    def __init__(self, data: dict):
        self.generated_at: str = data["generated_at"]
        self.municipalities: dict[str, Municipality] = {}
        self.provinces: dict[str, Province] = {}
        self._by_name: dict[str, list[Municipality]] = {}
        self._province_by_name: dict[str, Province] = {}

        for p in data["provinces"]:
            rows = p["municipalities"]
            total = sum(r[4] for r in rows) or 1
            province = Province(
                slug=p["slug"], name=p["name"],
                lat=round(sum(r[2] * r[4] for r in rows) / total, 3),
                lng=round(sum(r[3] * r[4] for r in rows) / total, 3),
                station_count=sum(r[4] for r in rows),
            )
            self.provinces[province.slug] = province
            for spelling in {province.name, *province.name.split("/"), province.slug.replace("-", " ")}:
                self._province_by_name.setdefault(normalize(spelling), province)

            for slug, name, lat, lng, count in rows:
                m = Municipality(slug, name, province.slug, province.name, lat, lng, count)
                self.municipalities[f"{province.slug}/{slug}"] = m
                for spelling in {name, *name.split("/")}:
                    self._by_name.setdefault(normalize(spelling), []).append(m)

        for alias, slug in PROVINCE_ALIASES.items():
            self._province_by_name.setdefault(alias, self.provinces[slug])
        for alias, slug in MUNICIPALITY_ALIASES.items():
            matches = [m for m in self.municipalities.values() if m.slug == slug]
            if matches and alias not in self._by_name:
                self._by_name[alias] = matches

        for matches in self._by_name.values():
            matches.sort(key=lambda m: -m.station_count)

    def find_province(self, text: str) -> Province | None:
        key = normalize(text)
        key = re.sub(r"^(provincia de|province of) ", "", key)
        if key in self._province_by_name:
            return self._province_by_name[key]
        close = difflib.get_close_matches(key, self._province_by_name, n=1, cutoff=0.85)
        return self._province_by_name[close[0]] if close else None

    def find_municipality(self, text: str) -> tuple[Municipality | None, list[Municipality]]:
        """The best match for a place name, and up to 4 other candidates.

        Accepts 'Lucena', 'Lucena, Córdoba' and 'Lucena (Córdoba), Spain'. A
        province after the comma or in brackets picks between towns that share
        a name. With no exact match it falls back to a close spelling, unless
        the name is a province's: 'Asturias' is not a typo of 'Asturianos'.
        """
        parts = [normalize(p) for p in re.split(r"[,()]", text) if normalize(p)]
        parts = [p for p in parts if p not in _SPAIN]
        if not parts:
            return None, []
        name, hints = parts[0], parts[1:]
        hint_provinces = {p.slug for p in (self.find_province(h) for h in hints) if p}

        matches = self._by_name.get(name, [])
        if not matches and name not in self._province_by_name:
            close = difflib.get_close_matches(name, self._by_name, n=3, cutoff=0.88)
            matches = [m for c in close for m in self._by_name[c]]
        if hint_provinces:
            preferred = [m for m in matches if m.province_slug in hint_provinces]
            matches = preferred + [m for m in matches if m not in preferred]
        if not matches:
            return None, []
        return matches[0], matches[1:5]

    def suggestions(self, text: str, n: int = 5) -> list[str]:
        name = normalize(re.split(r"[,(]", text)[0])
        close = difflib.get_close_matches(name, self._by_name, n=n, cutoff=0.6)
        return [self._by_name[c][0].label for c in close]


@cache
def gazetteer() -> Gazetteer:
    raw = resources.files("tankoup_mcp").joinpath("data/places.json").read_text(encoding="utf-8")
    return Gazetteer(json.loads(raw))
