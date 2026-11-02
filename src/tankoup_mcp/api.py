"""Client for the TankoUp API (https://api.tankoup.com), with a small TTL cache.

The MCP server owns no data: every price comes from the same API the TankoUp
apps and website use, which ingests the Spanish government's open feed.
"""

import time
from collections import OrderedDict
from typing import Any

import httpx

from tankoup_mcp.config import settings


class ApiError(Exception):
    """The API answered with an error. `code` is its machine-readable error, when it gives one."""

    def __init__(self, status: int, code: str | None, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class _TTLCache:
    def __init__(self, ttl_s: int, max_entries: int):
        self.ttl_s = ttl_s
        self.max_entries = max_entries
        self._items: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        hit = self._items.get(key)
        if hit is None or hit[0] < time.monotonic():
            self._items.pop(key, None)
            return None
        self._items.move_to_end(key)
        return hit[1]

    def put(self, key: str, value: Any) -> None:
        self._items[key] = (time.monotonic() + self.ttl_s, value)
        self._items.move_to_end(key)
        while len(self._items) > self.max_entries:
            self._items.popitem(last=False)


class TankoUpApi:
    def __init__(self, base_url: str, api_key: str, transport: httpx.AsyncBaseTransport | None = None):
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"X-API-Key": api_key, "Accept-Language": "en", "User-Agent": "tankoup-mcp"},
            timeout=settings.api_timeout_s,
            transport=transport,
        )
        self._cache = _TTLCache(settings.cache_ttl_s, settings.cache_max_entries)

    async def _request(self, method: str, path: str, *, params: dict | None = None, json: dict | None = None) -> Any:
        key = f"{method} {path} {sorted((params or {}).items())} {sorted((json or {}).items())}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        try:
            resp = await self._client.request(method, path, params=params, json=json)
        except httpx.HTTPError as exc:
            raise ApiError(503, "unavailable", "The TankoUp API did not answer. Try again in a minute.") from exc
        if resp.status_code >= 400:
            raise _error_from(resp)
        data = resp.json()
        self._cache.put(key, data)
        return data

    async def cheapest_area(self, lat: float, lng: float, fuel: str, radius_km: float, open_now: bool) -> dict:
        params = {"lat": round(lat, 4), "lng": round(lng, 4), "fuel": fuel, "radius_km": radius_km}
        if open_now:
            params["open_now"] = "true"
        return await self._request("GET", "/v1/cheapest/area", params=params)

    async def cheapest_route(self, origin: tuple[float, float], destination: tuple[float, float], fuel: str, open_now: bool) -> dict:
        body = {
            "origin": {"lat": round(origin[0], 4), "lng": round(origin[1], 4)},
            "destination": {"lat": round(destination[0], 4), "lng": round(destination[1], 4)},
            "fuel": fuel,
            "open_now": open_now,
        }
        return await self._request("POST", "/v1/cheapest/route", json=body)

    async def province(self, slug: str) -> dict:
        return await self._request("GET", f"/v1/provinces/{slug}")

    async def station(self, station_id: str, lat: float | None = None, lng: float | None = None) -> dict:
        params = {"lat": round(lat, 4), "lng": round(lng, 4)} if lat is not None and lng is not None else None
        return await self._request("GET", f"/v1/stations/{station_id}", params=params)

    async def aclose(self) -> None:
        await self._client.aclose()


def _error_from(resp: httpx.Response) -> ApiError:
    code, message = None, f"The TankoUp API answered {resp.status_code}."
    try:
        detail = resp.json().get("detail")
    except ValueError:
        detail = None
    if isinstance(detail, dict):
        code = detail.get("error")
        message = detail.get("message") or message
    elif isinstance(detail, str):
        message = detail
    if resp.status_code == 429:
        code, message = "rate_limited", "Too many requests right now. Try again in a minute."
    return ApiError(resp.status_code, code, message)


_api: TankoUpApi | None = None


def get_api() -> TankoUpApi:
    global _api
    if _api is None:
        _api = TankoUpApi(settings.api_url, settings.api_key)
    return _api


def set_api(api: TankoUpApi | None) -> None:
    """Swaps the client, for tests."""
    global _api
    _api = api
