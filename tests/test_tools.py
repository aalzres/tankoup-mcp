import json

import httpx
import pytest

from mcp import Client
from tests.conftest import fixture, not_found

pytestmark = pytest.mark.anyio


def text(result) -> str:
    return result.content[0].text


async def test_lists_four_read_only_tools_with_titles(client: Client):
    tools = (await client.list_tools()).tools

    assert sorted(t.name for t in tools) == [
        "find_cheapest_fuel_nearby",
        "find_cheapest_fuel_on_route",
        "get_province_fuel_prices",
        "get_station_details",
    ]
    for tool in tools:
        assert len(tool.name) <= 64
        assert tool.title and tool.annotations.title
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.destructive_hint is None
        assert tool.output_schema is not None
        assert "$defs" not in tool.input_schema
        for name, param in tool.input_schema["properties"].items():
            assert "type" in param or "anyOf" in param, f"{tool.name}.{name} has no type"


# --- find_cheapest_fuel_nearby ----------------------------------------------


async def test_nearby_resolves_a_town_and_returns_the_best_stations(client: Client, upstream):
    area = upstream.get("/v1/cheapest/area").respond(json=fixture("area"))

    result = await client.call_tool("find_cheapest_fuel_nearby", {"fuel": "diesel", "place": "Lucena, Córdoba", "limit": 3})

    assert not result.is_error
    request = area.calls.last.request
    assert request.headers["X-API-Key"] == "test-key"
    assert request.url.params["lat"] == "37.415" and request.url.params["lng"] == "-4.499"
    assert request.url.params["fuel"] == "diesel" and request.url.params["radius_km"] == "10"

    out = result.structured_content
    assert out["place"] == "Lucena (Córdoba)"
    assert out["fuel"] == "Diesel (Gasóleo A)"
    assert out["stations_found"] == 8
    assert len(out["stations"]) == 3
    first = out["stations"][0]
    assert first["id"] == "ES-9231"
    assert first["price_eur_per_litre"] == 1.749
    assert first["tankoup_url"] == "https://tankoup.com/es/app?station=ES-9231&fuel=diesel"
    assert first["directions_url"].startswith("https://www.google.com/maps/dir/?api=1&destination=37.41")
    assert out["more_on_tankoup"] == "https://tankoup.com/es/gasolineras/cordoba/lucena"
    assert 1.7 < out["area_average_eur_per_litre"] < 1.9
    assert out["best_saves_eur_on_40_litres"] >= 0


async def test_nearby_takes_coordinates_and_open_now(client: Client, upstream):
    area = upstream.get("/v1/cheapest/area").respond(json=fixture("area"))

    result = await client.call_tool(
        "find_cheapest_fuel_nearby",
        {"fuel": "sp95", "lat": 40.41678, "lng": -3.70379, "radius_km": 3, "open_now": True},
    )

    assert not result.is_error
    params = area.calls.last.request.url.params
    assert (params["lat"], params["lng"], params["fuel"], params["open_now"]) == ("40.4168", "-3.7038", "sp95", "true")
    assert result.structured_content["place"] == "40.4168, -3.7038"


async def test_nearby_answers_a_repeated_search_from_cache(client: Client, upstream):
    area = upstream.get("/v1/cheapest/area").respond(json=fixture("area"))

    for _ in range(3):
        await client.call_tool("find_cheapest_fuel_nearby", {"fuel": "diesel", "place": "Lucena"})

    assert area.call_count == 1


async def test_nearby_explains_an_unknown_place(client: Client):
    result = await client.call_tool("find_cheapest_fuel_nearby", {"fuel": "diesel", "place": "Santa Cruz"})

    assert result.is_error
    assert "'Santa Cruz' is not a Spanish town" in text(result)
    assert "Santa Cruz de" in text(result)
    assert "give lat/lng" in text(result)


async def test_nearby_points_a_province_to_the_province_tool(client: Client):
    result = await client.call_tool("find_cheapest_fuel_nearby", {"fuel": "diesel", "place": "Asturias"})

    assert result.is_error
    assert "is a province" in text(result) and "get_province_fuel_prices" in text(result)


async def test_nearby_needs_a_place_or_both_coordinates(client: Client):
    neither = await client.call_tool("find_cheapest_fuel_nearby", {"fuel": "diesel"})
    half = await client.call_tool("find_cheapest_fuel_nearby", {"fuel": "diesel", "lat": 40.4})

    assert neither.is_error and "place name or lat/lng" in text(neither)
    assert half.is_error and "both lat and lng" in text(half)


async def test_nearby_rejects_an_unknown_fuel_before_calling_the_api(client: Client, upstream):
    area = upstream.get("/v1/cheapest/area").respond(json=fixture("area"))

    result = await client.call_tool("find_cheapest_fuel_nearby", {"fuel": "hydrogen", "place": "Madrid"})

    assert result.is_error
    assert area.call_count == 0


async def test_nearby_suggests_a_wider_radius_when_nothing_is_in_range(client: Client, upstream):
    upstream.get("/v1/cheapest/area").mock(return_value=not_found("no_stations_in_range"))

    result = await client.call_tool("find_cheapest_fuel_nearby", {"fuel": "lpg", "place": "Soria", "radius_km": 5})

    assert result.is_error
    assert "LPG / autogas (GLP)" in text(result) and "within 5 km" in text(result) and "radius_km" in text(result)


async def test_nearby_says_when_a_point_is_outside_spain(client: Client, upstream):
    upstream.get("/v1/cheapest/area").mock(return_value=not_found("country_not_supported"))

    result = await client.call_tool("find_cheapest_fuel_nearby", {"fuel": "diesel", "lat": 48.85, "lng": 2.35})

    assert result.is_error and "only covers Spain" in text(result)


async def test_nearby_reports_an_api_outage_without_internals(client: Client, upstream):
    upstream.get("/v1/cheapest/area").mock(side_effect=httpx.ConnectError("boom"))

    result = await client.call_tool("find_cheapest_fuel_nearby", {"fuel": "diesel", "place": "Madrid"})

    assert result.is_error
    assert "did not answer" in text(result) and "boom" not in text(result)


# --- find_cheapest_fuel_on_route --------------------------------------------


async def test_route_sends_both_ends_and_links_directions_through_the_station(client: Client, upstream):
    route = upstream.post("/v1/cheapest/route").respond(json=fixture("route"))

    result = await client.call_tool("find_cheapest_fuel_on_route", {
        "origin": {"place": "Madrid"},
        "destination": {"lat": 37.8882, "lng": -4.7794},
        "fuel": "diesel",
        "limit": 2,
    })

    assert not result.is_error
    body = json.loads(route.calls.last.request.content)
    assert body["origin"]["lat"] == pytest.approx(40.42, abs=0.05) and body["origin"]["lng"] == pytest.approx(-3.69, abs=0.05)
    assert body["destination"] == {"lat": 37.8882, "lng": -4.7794}
    assert body["fuel"] == "diesel" and body["open_now"] is False

    out = result.structured_content
    assert out["origin"] == "Madrid" and out["destination"] == "37.8882, -4.7794"
    assert (out["route_km"], out["duration_min"], out["stations_found"]) == (396.4, 245, 6)
    assert len(out["stations"]) == 2
    directions = out["stations"][0]["directions_url"]
    assert "origin=" in directions and "destination=37.8882,-4.7794" in directions and "waypoints=" in directions
    assert "leave the route" in out["ranking"]


async def test_route_stops_at_the_daily_limit(client: Client, upstream):
    from tankoup_mcp.server import route_budget

    route = upstream.post("/v1/cheapest/route").respond(json=fixture("route"))
    route_budget.limit = 1
    try:
        args = {"origin": {"place": "Madrid"}, "destination": {"place": "Toledo"}, "fuel": "diesel"}
        first = await client.call_tool("find_cheapest_fuel_on_route", args)
        second = await client.call_tool("find_cheapest_fuel_on_route", args | {"fuel": "sp95"})
    finally:
        route_budget.limit = 100

    assert not first.is_error
    assert second.is_error and "today's limit" in text(second)
    assert route.call_count == 1


async def test_route_explains_a_missing_route(client: Client, upstream):
    upstream.post("/v1/cheapest/route").mock(return_value=not_found("no_route"))

    result = await client.call_tool("find_cheapest_fuel_on_route", {
        "origin": {"place": "Palma"}, "destination": {"place": "Madrid"}, "fuel": "diesel",
    })

    assert result.is_error and "no driving route" in text(result)


async def test_route_names_the_end_it_could_not_place(client: Client):
    result = await client.call_tool("find_cheapest_fuel_on_route", {
        "origin": {"place": "Madrid"}, "destination": {}, "fuel": "diesel",
    })

    assert result.is_error and "for the destination" in text(result)


# --- get_province_fuel_prices -----------------------------------------------


async def test_province_by_its_old_spanish_name_for_one_fuel(client: Client, upstream):
    province = upstream.get("/v1/provinces/bizkaia").respond(json=fixture("province"))

    result = await client.call_tool("get_province_fuel_prices", {"province": "Vizcaya", "fuel": "sp95"})

    assert not result.is_error and province.called
    out = result.structured_content
    assert out["province"] == "Bizkaia"
    assert [f["fuel"] for f in out["fuels"]] == ["sp95"]
    sp95 = out["fuels"][0]
    assert sp95["average_eur_per_litre"] == 1.743 and sp95["lowest_eur_per_litre"] == 1.499
    assert sp95["cheapest_brand"].startswith("BALLENOIL")
    assert len(sp95["cheapest_stations"]) == 3
    assert out["more_on_tankoup"] == "https://tankoup.com/es/gasolineras/bizkaia/gasolina-95"


async def test_province_without_a_fuel_returns_every_fuel(client: Client, upstream):
    upstream.get("/v1/provinces/bizkaia").respond(json=fixture("province"))

    result = await client.call_tool("get_province_fuel_prices", {"province": "bizkaia"})

    fuels = [f["fuel"] for f in result.structured_content["fuels"]]
    assert set(fuels) == set(fixture("province")["fuels"])
    assert result.structured_content["more_on_tankoup"] == "https://tankoup.com/es/gasolineras/bizkaia"


async def test_province_rejects_a_name_that_is_not_one(client: Client):
    result = await client.call_tool("get_province_fuel_prices", {"province": "Catalonia"})

    assert result.is_error and "not a Spanish province" in text(result)


# --- get_station_details ----------------------------------------------------


async def test_station_details_with_hours_prices_and_distance(client: Client, upstream):
    data = fixture("station") | {"distance_km": 12.345}
    station = upstream.get("/v1/stations/ES-6493").respond(json=data)

    result = await client.call_tool("get_station_details", {"station_id": "es-6493", "lat": 37.4, "lng": -4.4})

    assert not result.is_error
    assert station.calls.last.request.url.params["lat"] == "37.4"
    out = result.structured_content
    assert out["id"] == "ES-6493"
    assert out["opening_hours"] == "Mon–Sun 06:00–22:00"
    assert [p["fuel"] for p in out["prices"]] == ["diesel", "diesel_premium", "sp95", "sp98"]
    assert out["distance_km"] == 12.3
    assert out["tankoup_url"] == "https://tankoup.com/es/app?station=ES-6493"


async def test_station_details_for_an_unknown_id(client: Client, upstream):
    upstream.get("/v1/stations/ES-0").respond(404, json={"detail": "Station not found"})

    result = await client.call_tool("get_station_details", {"station_id": "ES-0"})

    assert result.is_error and "No station with id 'ES-0'" in text(result)


async def test_station_details_rejects_a_malformed_id(client: Client, upstream):
    result = await client.call_tool("get_station_details", {"station_id": "../../v1/reports"})

    assert result.is_error
    assert not upstream.calls
