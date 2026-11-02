"""Calls every tool on a running server and prints a line per call.

    uv run python scripts/smoke.py https://mcp.tankoup.com/mcp
"""

import sys

import anyio

from mcp import Client

CALLS = [
    ("find_cheapest_fuel_nearby", {"fuel": "diesel", "place": "Lucena, Córdoba", "limit": 3}),
    ("find_cheapest_fuel_nearby", {"fuel": "sp95", "lat": 40.4168, "lng": -3.7038, "radius_km": 3, "open_now": True}),
    ("find_cheapest_fuel_on_route", {"origin": {"place": "Madrid"}, "destination": {"place": "Valencia"}, "fuel": "sp95", "limit": 3}),
    ("get_province_fuel_prices", {"province": "Vizcaya", "fuel": "diesel"}),
    ("get_station_details", {"station_id": "ES-3213"}),
]


async def main(url: str) -> int:
    failures = 0
    async with Client(url) as client:
        tools = (await client.list_tools()).tools
        print(f"{url}: {len(tools)} tools, protocol {client.protocol_version}")
        for name, args in CALLS:
            result = await client.call_tool(name, args)
            out = result.structured_content or {}
            if result.is_error:
                failures += 1
                summary = result.content[0].text
            elif "stations" in out:
                first = out["stations"][0]
                summary = f"{out['stations_found']} found; best {first['name']} {first['price_eur_per_litre']} €/L"
            elif "fuels" in out:
                f = out["fuels"][0]
                summary = f"{out['province']} {f['fuel']} avg {f['average_eur_per_litre']} min {f['lowest_eur_per_litre']}"
            else:
                summary = f"{out.get('name')}: {len(out.get('prices', []))} prices, {out.get('opening_hours')}"
            print(f"{'FAIL' if result.is_error else 'ok  '} {name}: {summary}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(anyio.run(main, sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/mcp"))
