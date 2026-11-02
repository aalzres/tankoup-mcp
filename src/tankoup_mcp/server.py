"""The TankoUp MCP server: four read-only tools over Spain's fuel prices."""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from importlib.metadata import version
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from mcp.server import MCPServer
from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, Icon, TextContent, ToolAnnotations

from tankoup_mcp import links
from tankoup_mcp.api import ApiError, get_api
from tankoup_mcp.config import settings
from tankoup_mcp.places import Municipality, gazetteer

log = logging.getLogger("tankoup_mcp")

Fuel = Literal["diesel", "diesel_premium", "sp95", "sp95_e10", "sp98", "lpg"]

FUEL_LABELS: dict[str, str] = {
    "diesel": "Diesel (Gasóleo A)",
    "diesel_premium": "Premium diesel (Gasóleo Premium)",
    "sp95": "Petrol 95 E5 (Gasolina 95)",
    "sp95_e10": "Petrol 95 E10 (Gasolina 95 E10)",
    "sp98": "Petrol 98 (Gasolina 98)",
    "lpg": "LPG / autogas (GLP)",
}

FUEL_DESCRIPTION = (
    "Fuel type: diesel = Gasóleo A (regular diesel), diesel_premium = Gasóleo Premium, "
    "sp95 = Gasolina 95 E5 (regular unleaded petrol), sp95_e10 = Gasolina 95 E10, "
    "sp98 = Gasolina 98, lpg = GLP / autogas."
)

# How the API ranks stations: what you pay at the pump plus the fuel burned
# getting there and back (40 L fill, 7 L/100 km), so a cheap station far away
# can rank below a slightly dearer one around the corner.
RANKING = "Total cost: pump price for a 40 L fill plus the fuel used to drive there and back."

READ_ONLY = dict(read_only_hint=True, open_world_hint=False)


# --- Logging ----------------------------------------------------------------


async def log_calls(ctx: ServerRequestContext, call_next: CallNext) -> HandlerResult:
    """One line per request: method, tool, protocol and time. Never the arguments."""
    start = time.perf_counter()
    try:
        return await call_next(ctx)
    finally:
        if ctx.method == "tools/call":
            tool = (ctx.params or {}).get("name")
            log.info("%s %s protocol=%s %.0fms", ctx.method, tool, ctx.protocol_version,
                     (time.perf_counter() - start) * 1000)

mcp = MCPServer(
    name="tankoup",
    title="TankoUp",
    description="Cheapest fuel in Spain: live prices for every petrol station, from the Spanish government's open data.",
    instructions=(
        "TankoUp has the current price of every fuel at about 12,000 petrol stations in Spain, from the "
        "Spanish government's open data (MITECO), refreshed every 4 hours. Prices are in euros per litre. "
        "Coverage is Spain only: mainland, Balearic and Canary Islands, Ceuta and Melilla. Places are "
        "Spanish towns and cities by name, or any point by latitude and longitude. Station ids returned "
        "by the search tools work in get_station_details."
    ),
    website_url="https://tankoup.com",
    icons=[
        Icon(src="https://tankoup.com/icon.svg", mime_type="image/svg+xml", sizes=["any"]),
        Icon(src="https://tankoup.com/apple-icon.png", mime_type="image/png", sizes=["180x180"]),
    ],
    version=version("tankoup-mcp"),
    middleware=[log_calls],
)


# --- Output shapes ----------------------------------------------------------


class Station(BaseModel):
    id: str = Field(description="TankoUp station id, for get_station_details.")
    name: str
    brand: str | None
    address: str
    price_eur_per_litre: float
    distance_km: float = Field(description="Straight-line distance from the search point.")
    open_now: bool | None = Field(description="null when the opening hours are unknown.")
    tankoup_url: str
    directions_url: str


class NearbyResult(BaseModel):
    place: str = Field(description="Where the search was centred, as understood.")
    fuel: str
    radius_km: float
    stations_found: int
    stations: list[Station] = Field(description="Best first, by total cost.")
    ranking: str
    area_average_eur_per_litre: float
    best_saves_eur_on_40_litres: float = Field(description="Saving at the first station against the area average.")
    prices_updated_at: datetime
    other_places_with_this_name: list[str] = []
    more_on_tankoup: str


class RouteResult(BaseModel):
    origin: str
    destination: str
    fuel: str
    route_km: float
    duration_min: int
    stations_found: int = Field(description="Stations within about 3 km of the route.")
    stations: list[Station] = Field(description="Best first, by total cost. distance_km is from the origin.")
    ranking: str
    route_average_eur_per_litre: float
    best_saves_eur_on_40_litres: float = Field(description="Saving at the first station against the route average.")
    prices_updated_at: datetime


class ProvinceStation(BaseModel):
    id: str
    name: str
    town: str
    price_eur_per_litre: float
    tankoup_url: str


class ProvinceFuel(BaseModel):
    fuel: str
    label: str
    average_eur_per_litre: float
    lowest_eur_per_litre: float
    stations: int
    change_30d_pct: float | None = Field(description="Change of the average in the last 30 days. null without history.")
    vs_spain_average_pct: float = Field(description="Positive means dearer than the Spanish average.")
    cheapest_brand: str | None
    cheapest_stations: list[ProvinceStation]


class ProvinceResult(BaseModel):
    province: str
    fuels: list[ProvinceFuel]
    prices_updated_at: datetime
    more_on_tankoup: str


class FuelPrice(BaseModel):
    fuel: str
    label: str
    price_eur_per_litre: float
    updated_at: datetime


class StationDetail(BaseModel):
    id: str
    name: str
    brand: str | None
    address: str
    town: str | None
    province: str | None
    lat: float
    lng: float
    open_now: bool | None = Field(description="null when the opening hours are unknown.")
    opening_hours: str | None = Field(description="null when unknown.")
    prices: list[FuelPrice]
    distance_km: float | None = Field(description="From the given lat/lng, straight line. null without them.")
    tankoup_url: str
    directions_url: str


class Location(BaseModel):
    place: str | None = Field(
        default=None,
        description="A Spanish town or city, optionally with its province to tell apart towns with the "
                    "same name: 'Lucena, Córdoba'.",
    )
    lat: float | None = Field(default=None, ge=-90, le=90, description="Latitude, with lng, for any point.")
    lng: float | None = Field(default=None, ge=-180, le=180, description="Longitude, with lat.")


# --- Helpers ----------------------------------------------------------------


@dataclass
class _Point:
    lat: float
    lng: float
    label: str
    municipality: Municipality | None = None
    others: list[str] = field(default_factory=list)


def _resolve(place: str | None, lat: float | None, lng: float | None, what: str = "the search") -> _Point:
    if (lat is None) != (lng is None):
        raise ToolError(f"Give both lat and lng for {what}, or a place name.")
    if lat is not None and lng is not None:
        return _Point(lat=lat, lng=lng, label=place or f"{lat:.4f}, {lng:.4f}")
    if not place or not place.strip():
        raise ToolError(f"Give a place name or lat/lng for {what}.")

    g = gazetteer()
    best, others = g.find_municipality(place)
    if best is None:
        province = g.find_province(place)
        if province is not None:
            raise ToolError(
                f"'{place}' is a province. For prices across it use get_province_fuel_prices; "
                f"for stations near a point, name a town in it or give lat/lng."
            )
        hint = g.suggestions(place)
        hint_text = f" Close names: {', '.join(hint)}." if hint else ""
        raise ToolError(
            f"'{place}' is not a Spanish town with a fuel station.{hint_text} "
            f"For a street, landmark or anywhere else, give lat/lng instead."
        )
    return _Point(lat=best.lat, lng=best.lng, label=best.label, municipality=best, others=[m.label for m in others])


def _api_error(exc: ApiError, fuel: str | None = None, radius_km: float | None = None) -> ToolError:
    label = FUEL_LABELS.get(fuel or "", "this fuel")
    match exc.code:
        case "country_not_supported":
            return ToolError("TankoUp only covers Spain: mainland, Balearic and Canary Islands, Ceuta and Melilla.")
        case "no_stations_in_range":
            more = " Try a larger radius_km (up to 50)." if radius_km and radius_km < 50 else ""
            return ToolError(f"No station sells {label} with a current price within {radius_km:g} km.{more}")
        case "no_stations_on_route":
            return ToolError(f"No station along this route sells {label} with a current price.")
        case "no_route":
            return ToolError("There is no driving route between those two places.")
        case "route_too_long" | "rate_limited" | "unavailable":
            return ToolError(exc.message)
    if exc.status == 503:
        return ToolError("Route search is unavailable right now. Try again later.")
    return ToolError(exc.message)


def _address(station: dict) -> str:
    parts = [station.get("address"), station.get("city")]
    return ", ".join(p.strip().title() if p.isupper() else p.strip() for p in parts if p)


def _brand(station: dict) -> str | None:
    """None when it only repeats the name, as with most independents and BALLENOIL."""
    brand = station.get("brand")
    return None if not brand or brand.strip().lower() == station["name"].strip().lower() else brand


def _station(item: dict, fuel: str, *, origin: tuple[float, float] | None = None,
             destination: tuple[float, float] | None = None) -> Station:
    s = item["station"]
    return Station(
        id=s["id"],
        name=s["name"],
        brand=_brand(s),
        address=_address(s),
        price_eur_per_litre=item["price"]["amount"],
        distance_km=round(item["distance_km"], 1),
        open_now=item.get("is_open"),
        tankoup_url=links.station_url(s["id"], fuel),
        directions_url=links.directions_url(s["lat"], s["lng"], origin, destination),
    )


def _average(items: list[dict]) -> float:
    return round(sum(i["price"]["amount"] for i in items) / len(items), 3)


def _latest(items: list[dict]) -> datetime:
    return max(datetime.fromisoformat(i["price"]["updated_at"]) for i in items)


DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _opening_hours(schedule: dict | None) -> str | None:
    if not schedule:
        return None
    if schedule.get("always_open"):
        return "Open 24 hours"
    out = []
    for period in schedule.get("periods", []):
        days = sorted(period["days"])
        if days == list(range(days[0], days[-1] + 1)) and len(days) > 2:
            day_text = f"{DAYS[days[0]]}–{DAYS[days[-1]]}"
        else:
            day_text = ", ".join(DAYS[d] for d in days)
        out.append(f"{day_text} {period['open']}–{period['close']}")
    return "; ".join(out) or None


def _result(out: BaseModel) -> CallToolResult:
    """The same data twice, as the SDK would, but with compact JSON for the model to read."""
    data = out.model_dump(mode="json")
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return CallToolResult(content=[TextContent(type="text", text=text)], structured_content=data)


# --- Tools ------------------------------------------------------------------


@mcp.tool(
    title="Cheapest fuel near a place",
    annotations=ToolAnnotations(title="Cheapest fuel near a place", **READ_ONLY),
)
async def find_cheapest_fuel_nearby(
    fuel: Annotated[Fuel, Field(description=FUEL_DESCRIPTION)],
    place: Annotated[str | None, Field(
        description="A Spanish town or city, optionally with its province: 'Lucena, Córdoba'. "
                    "Use lat/lng instead for a street, landmark or the user's position.",
    )] = None,
    lat: Annotated[float | None, Field(ge=-90, le=90, description="Latitude of the search point.")] = None,
    lng: Annotated[float | None, Field(ge=-180, le=180, description="Longitude of the search point.")] = None,
    radius_km: Annotated[float, Field(ge=1, le=50, description="Search radius in km.")] = 10,
    open_now: Annotated[bool, Field(description="Only stations open right now (unknown hours count as open).")] = False,
    limit: Annotated[int, Field(ge=1, le=10, description="How many stations to return.")] = 5,
) -> Annotated[CallToolResult, NearbyResult]:
    """Find the cheapest petrol stations in Spain near a town, city or point, for one fuel.

    Returns the best stations by total cost (price plus the fuel used to get
    there), each with its price per litre, distance, whether it is open, and
    links to TankoUp and to directions.
    """
    point = _resolve(place, lat, lng)
    try:
        data = await get_api().cheapest_area(point.lat, point.lng, fuel, radius_km, open_now)
    except ApiError as exc:
        raise _api_error(exc, fuel, radius_km) from None

    items = data["stations"]
    m = point.municipality
    return _result(NearbyResult(
        place=point.label,
        fuel=FUEL_LABELS[fuel],
        radius_km=radius_km,
        stations_found=len(items),
        stations=[_station(i, fuel) for i in items[:limit]],
        ranking=RANKING,
        area_average_eur_per_litre=_average(items),
        best_saves_eur_on_40_litres=max(items[0]["savings_eur"], 0),
        prices_updated_at=_latest(items),
        other_places_with_this_name=point.others,
        more_on_tankoup=links.municipality_url(m.province_slug, m.slug) if m else links.station_url(items[0]["station"]["id"], fuel),
    ))


class _RouteBudget:
    """Route searches per instance per UTC day: each one costs a Google Routes call upstream."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.day = ""
        self.used = 0

    def take(self) -> bool:
        today = time.strftime("%Y-%m-%d", time.gmtime())
        if today != self.day:
            self.day, self.used = today, 0
        if self.used >= self.limit:
            return False
        self.used += 1
        return True


route_budget = _RouteBudget(settings.route_daily_limit)


@mcp.tool(
    title="Cheapest fuel along a route",
    annotations=ToolAnnotations(title="Cheapest fuel along a route", **READ_ONLY),
)
async def find_cheapest_fuel_on_route(
    origin: Annotated[Location, Field(description="Where the trip starts: a place name, or lat/lng.")],
    destination: Annotated[Location, Field(description="Where the trip ends: a place name, or lat/lng.")],
    fuel: Annotated[Fuel, Field(description=FUEL_DESCRIPTION)],
    open_now: Annotated[bool, Field(description="Only stations open right now (unknown hours count as open).")] = False,
    limit: Annotated[int, Field(ge=1, le=10, description="How many stations to return.")] = 5,
) -> Annotated[CallToolResult, RouteResult]:
    """Find the cheapest petrol stations along a driving route in Spain, for one fuel.

    Works out the driving route and returns the best stations within about
    3 km of it, by total cost including the detour, with links to TankoUp and
    to directions through the station. Routes up to 1,200 km.
    """
    start = _resolve(origin.place, origin.lat, origin.lng, "the origin")
    end = _resolve(destination.place, destination.lat, destination.lng, "the destination")
    if not route_budget.take():
        raise ToolError("Route search has reached today's limit on this server. Try again tomorrow.")
    try:
        data = await get_api().cheapest_route((start.lat, start.lng), (end.lat, end.lng), fuel, open_now)
    except ApiError as exc:
        raise _api_error(exc, fuel) from None

    items = data["stations"]
    trip = ((start.lat, start.lng), (end.lat, end.lng))
    return _result(RouteResult(
        origin=start.label,
        destination=end.label,
        fuel=FUEL_LABELS[fuel],
        route_km=data["route"]["route_km"],
        duration_min=data["route"]["duration_min"],
        stations_found=len(items),
        stations=[_station(i, fuel, origin=trip[0], destination=trip[1]) for i in items[:limit]],
        ranking=RANKING.replace("drive there and back", "leave the route and rejoin it"),
        route_average_eur_per_litre=_average(items),
        best_saves_eur_on_40_litres=max(items[0]["savings_eur"], 0),
        prices_updated_at=_latest(items),
    ))


@mcp.tool(
    title="Fuel prices in a province",
    annotations=ToolAnnotations(title="Fuel prices in a province", **READ_ONLY),
)
async def get_province_fuel_prices(
    province: Annotated[str, Field(
        description="One of Spain's 50 provinces, or Ceuta or Melilla, in Spanish, English or the "
                    "regional language: 'Córdoba', 'Vizcaya', 'Illes Balears', 'Seville'.",
    )],
    fuel: Annotated[Fuel | None, Field(description=FUEL_DESCRIPTION + " Leave out for every fuel.")] = None,
) -> Annotated[CallToolResult, ProvinceResult]:
    """Average and lowest fuel prices in a Spanish province, with its cheapest stations.

    For each fuel: the average and lowest price per litre, the change over the
    last 30 days, how it compares with the Spanish average, the cheapest brand
    and the 3 cheapest stations.
    """
    found = gazetteer().find_province(province)
    if found is None:
        raise ToolError(f"'{province}' is not a Spanish province. Examples: Madrid, Barcelona, Valencia, Sevilla, Bizkaia.")
    try:
        data = await get_api().province(found.slug)
    except ApiError as exc:
        raise _api_error(exc, fuel) from None

    fuels = []
    for key, insight in data["fuels"].items():
        if fuel and key != fuel:
            continue
        brand = insight.get("cheapest_brand")
        fuels.append(ProvinceFuel(
            fuel=key,
            label=FUEL_LABELS.get(key, key),
            average_eur_per_litre=insight["current_avg"],
            lowest_eur_per_litre=insight["current_min"],
            stations=insight["station_count"],
            change_30d_pct=insight.get("trend_30d_pct"),
            vs_spain_average_pct=insight["vs_national_pct"],
            cheapest_brand=f"{brand['name']} ({brand['avg_price']:.3f} €/L on average)" if brand else None,
            cheapest_stations=[
                ProvinceStation(
                    id=s["id"], name=s["name"], town=s["city"], price_eur_per_litre=s["price"],
                    tankoup_url=links.station_url(s["id"], key),
                )
                for s in insight["cheapest_stations"][:3]
            ],
        ))
    if not fuels:
        raise ToolError(f"No station in {data['name']} sells {FUEL_LABELS.get(fuel or '', 'that fuel')}.")

    return _result(ProvinceResult(
        province=data["name"],
        fuels=fuels,
        prices_updated_at=data["generated_at"],
        more_on_tankoup=links.province_url(found.slug, fuel),
    ))


@mcp.tool(
    title="Petrol station details",
    annotations=ToolAnnotations(title="Petrol station details", **READ_ONLY),
)
async def get_station_details(
    station_id: Annotated[str, Field(
        pattern=r"^[A-Za-z]{2}-[A-Za-z0-9]+$",
        description="Station id from another TankoUp tool, like 'ES-3213'.",
    )],
    lat: Annotated[float | None, Field(ge=-90, le=90, description="Optional: the user's latitude, for the distance.")] = None,
    lng: Annotated[float | None, Field(ge=-180, le=180, description="Optional: the user's longitude.")] = None,
) -> Annotated[CallToolResult, StationDetail]:
    """Everything about one petrol station: every fuel's current price, opening hours, address and links."""
    try:
        data = await get_api().station(station_id.upper(), lat, lng)
    except ApiError as exc:
        if exc.status == 404:
            raise ToolError(f"No station with id '{station_id}'. Ids come from the other TankoUp tools.") from None
        raise _api_error(exc) from None

    s = data["station"]
    return _result(StationDetail(
        id=s["id"],
        name=s["name"],
        brand=_brand(s),
        address=_address({"address": s.get("address")}),
        town=s.get("city"),
        province=s.get("province").title() if s.get("province") else None,
        lat=s["lat"],
        lng=s["lng"],
        open_now=data.get("is_open"),
        opening_hours=_opening_hours(s.get("schedule")),
        prices=[
            FuelPrice(fuel=p["fuel_type"], label=FUEL_LABELS.get(p["fuel_type"], p["fuel_type"]),
                      price_eur_per_litre=p["amount"], updated_at=p["updated_at"])
            for p in data["prices"]
        ],
        distance_km=round(data["distance_km"], 1) if data.get("distance_km") is not None else None,
        tankoup_url=links.station_url(s["id"]),
        directions_url=links.directions_url(s["lat"], s["lng"]),
    ))
