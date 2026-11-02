import json
from pathlib import Path

import httpx
import pytest
import respx

from mcp import Client
from tankoup_mcp.api import TankoUpApi, set_api
from tankoup_mcp.server import mcp, route_budget

API = "https://api.test"
FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def upstream():
    """The TankoUp API, mocked. Every test gets a fresh client, so nothing is cached between tests."""
    with respx.mock(base_url=API, assert_all_called=False) as router:
        set_api(TankoUpApi(API, "test-key"))
        route_budget.day, route_budget.used = "", 0
        yield router
        set_api(None)


@pytest.fixture
async def client(upstream):
    async with Client(mcp, raise_exceptions=True) as c:
        yield c


def not_found(code: str, message: str = "") -> httpx.Response:
    return httpx.Response(404, json={"detail": {"error": code, "message": message}})
