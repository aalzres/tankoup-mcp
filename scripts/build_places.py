"""Builds src/tankoup_mcp/data/places.json, the gazetteer place names resolve against.

Every Spanish municipality with at least one fuel station, with the average
position of its stations, read from the TankoUp API: the taxonomy once, then
one province detail per province (53 requests in all).

    TANKOUP_API_KEY=... uv run python scripts/build_places.py

Municipalities change when a town gets its first station or loses its last
one, so a rebuild every few months is enough.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

OUT = Path(__file__).resolve().parent.parent / "src" / "tankoup_mcp" / "data" / "places.json"


def main() -> int:
    base = os.environ.get("TANKOUP_API_URL", "https://api.tankoup.com").rstrip("/")
    key = os.environ.get("TANKOUP_API_KEY")
    if not key:
        print("TANKOUP_API_KEY is not set", file=sys.stderr)
        return 1

    with httpx.Client(base_url=base, headers={"X-API-Key": key}, timeout=30) as client:
        taxonomy = client.get("/v1/provinces").raise_for_status().json()
        provinces = []
        for item in taxonomy["provinces"]:
            detail = client.get(f"/v1/provinces/{item['slug']}").raise_for_status().json()
            provinces.append({
                "slug": detail["slug"],
                "name": detail["name"],
                # [slug, name, lat, lng, station_count], biggest first
                "municipalities": [
                    [m["slug"], m["name"], m["lat"], m["lng"], m["station_count"]]
                    for m in sorted(detail["municipalities"], key=lambda m: -m["station_count"])
                ],
            })

    OUT.write_text(json.dumps(
        {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "provinces": provinces},
        ensure_ascii=False, separators=(",", ":"),
    ) + "\n")
    count = sum(len(p["municipalities"]) for p in provinces)
    print(f"{OUT.name}: {len(provinces)} provinces, {count} municipalities, {OUT.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
