"""The HTTP surface Cloud Run serves: MCP over Streamable HTTP, limits and plain routes."""

import httpx
import pytest

from tankoup_mcp.app import RateLimit, client_ip, create_app
from tests.conftest import fixture

pytestmark = pytest.mark.anyio

INIT = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}},
}
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture
async def http(upstream):
    app = create_app()
    starlette_app = app.app.app  # CORS -> RateLimit -> Starlette
    async with starlette_app.router.lifespan_context(starlette_app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="https://mcp.tankoup.com") as c:
            yield c


async def test_a_legacy_client_initializes_and_calls_a_tool_without_a_session(http, upstream):
    upstream.get("/v1/cheapest/area").respond(json=fixture("area"))

    init = await http.post("/mcp", json=INIT, headers=HEADERS)
    assert init.status_code == 200
    assert init.json()["result"]["serverInfo"]["name"] == "tankoup"
    assert "mcp-session-id" not in init.headers

    call = await http.post("/mcp", headers=HEADERS | {"MCP-Protocol-Version": "2025-06-18"}, json={
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "find_cheapest_fuel_nearby", "arguments": {"fuel": "diesel", "place": "Lucena"}},
    })
    assert call.status_code == 200
    result = call.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["stations"][0]["id"] == "ES-9231"


async def test_any_host_is_accepted_behind_cloud_run(http):
    response = await http.post("/mcp", json=INIT, headers=HEADERS | {"Host": "tankoup-mcp-x.a.run.app"})
    assert response.status_code == 200


async def test_health_and_landing(http):
    assert (await http.get("/health")).json() == {"status": "ok"}
    landing = (await http.get("/")).json()
    assert landing["mcp_endpoint"] == "https://mcp.tankoup.com/mcp"


async def test_openai_challenge_is_served_only_when_configured(http, monkeypatch):
    from tankoup_mcp import app as app_module

    assert (await http.get("/.well-known/openai-apps-challenge")).status_code == 404
    monkeypatch.setattr(app_module, "settings", type("S", (), {"openai_apps_challenge": "tok-123"})())
    response = await http.get("/.well-known/openai-apps-challenge")
    assert response.status_code == 200 and response.text == "tok-123"


async def test_cors_preflight_is_open(http):
    response = await http.options("/mcp", headers={
        "Origin": "https://inspector.example", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,mcp-protocol-version",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"


async def test_rate_limit_per_ip_answers_429_with_retry_after():
    async def ok(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    limited = RateLimit(ok, per_ip=2, global_=100)
    transport = httpx.ASGITransport(app=limited)
    async with httpx.AsyncClient(transport=transport, base_url="http://x") as c:
        codes = [(await c.post("/mcp", headers={"X-Forwarded-For": "1.1.1.1"})).status_code for _ in range(3)]
        other = (await c.post("/mcp", headers={"X-Forwarded-For": "2.2.2.2"})).status_code
        last = await c.post("/mcp", headers={"X-Forwarded-For": "1.1.1.1"})
        health = (await c.get("/health", headers={"X-Forwarded-For": "1.1.1.1"})).status_code

    assert codes == [200, 200, 429]
    assert other == 200
    assert last.status_code == 429 and int(last.headers["retry-after"]) <= 60
    assert last.json()["error"]["message"].startswith("Rate limit exceeded")
    assert health == 200


async def test_rate_limit_for_the_whole_instance():
    async def ok(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    limited = RateLimit(ok, per_ip=100, global_=3)
    transport = httpx.ASGITransport(app=limited)
    async with httpx.AsyncClient(transport=transport, base_url="http://x") as c:
        codes = [(await c.post("/mcp", headers={"X-Forwarded-For": f"10.0.0.{i}"})).status_code for i in range(4)]

    assert codes == [200, 200, 200, 429]


def test_client_ip_trusts_only_the_last_forwarded_hop():
    scope = {"headers": [(b"x-forwarded-for", b"6.6.6.6, 203.0.113.9")], "client": ("10.0.0.1", 1)}
    assert client_ip(scope) == "203.0.113.9"
    assert client_ip({"headers": [], "client": ("10.0.0.1", 1)}) == "10.0.0.1"


def test_client_ip_behind_cloudflare_is_the_connecting_ip():
    scope = {"headers": [(b"x-forwarded-for", b"198.51.100.7, 162.158.1.1"), (b"cf-connecting-ip", b"198.51.100.7")]}
    assert client_ip(scope) == "198.51.100.7"
