"""Links to tankoup.com, to the app stores and to turn-by-turn directions."""

from urllib.parse import urlencode

SITE = "https://tankoup.com"

# Tags every link into TankoUp, so its analytics can tell visits and installs that came through an
# AI assistant. Google Maps links stay untagged: they are not ours.
UTM = {"utm_source": "mcp", "utm_medium": "assistant"}

# Spanish storefront, as on tankoup.com: Apple 404s the country-less form.
APP_STORE_URL = "https://apps.apple.com/es/app/tankoup/id6789885475"

# The Play Store hands `referrer` to the install, where Firebase Analytics reads the UTM tags.
GOOGLE_PLAY_URL = "https://play.google.com/store/apps/details?" + urlencode(
    {"id": "com.tankoup.app", "referrer": urlencode(UTM)})

# The website's content pages name fuels with these slugs (tanko-web, FUEL_SLUGS).
FUEL_SLUGS = {
    "diesel": "diesel",
    "diesel_premium": "diesel-premium",
    "sp95": "gasolina-95",
    "sp95_e10": "gasolina-95-e10",
    "sp98": "gasolina-98",
    "lpg": "glp",
}


def station_url(station_id: str, fuel: str | None = None) -> str:
    """Opens the station in the TankoUp web app, or in the native app where installed."""
    query = {"station": station_id} | ({"fuel": fuel} if fuel else {}) | UTM
    return f"{SITE}/es/app?{urlencode(query)}"


def province_url(province_slug: str, fuel: str | None = None) -> str:
    path = f"/es/gasolineras/{province_slug}" + (f"/{FUEL_SLUGS[fuel]}" if fuel else "")
    return f"{SITE}{path}?{urlencode(UTM)}"


def municipality_url(province_slug: str, municipality_slug: str) -> str:
    return f"{SITE}/es/gasolineras/{province_slug}/{municipality_slug}?{urlencode(UTM)}"


def directions_url(lat: float, lng: float, origin: tuple[float, float] | None = None,
                   destination: tuple[float, float] | None = None) -> str:
    """Google Maps directions to a station, or through it when the trip has an origin and destination."""
    if origin and destination:
        params = {
            "api": "1",
            "origin": f"{origin[0]},{origin[1]}",
            "destination": f"{destination[0]},{destination[1]}",
            "waypoints": f"{lat},{lng}",
        }
    else:
        params = {"api": "1", "destination": f"{lat},{lng}"}
    return f"https://www.google.com/maps/dir/?{urlencode(params, safe=',')}"
