"""The ASGI app Cloud Run serves: MCP at /mcp, plus a health check and a landing response.

    uv run uvicorn tankoup_mcp.app:app --port 8000
"""

import json
import logging
import time
from collections import defaultdict

from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from mcp.server.transport_security import TransportSecuritySettings

from tankoup_mcp.config import settings
from tankoup_mcp.server import mcp

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
# httpx logs every upstream URL at INFO, and those carry the coordinates searched.
logging.getLogger("httpx").setLevel(logging.WARNING)

REPO_URL = "https://github.com/aalzres/tankoup-mcp"


@mcp.custom_route("/", methods=["GET"], include_in_schema=False)
async def root(request: Request) -> Response:
    return JSONResponse({
        "name": "TankoUp MCP server",
        "mcp_endpoint": str(request.url_for("root")).rstrip("/") + "/mcp",
        "about": "Cheapest fuel in Spain for Claude, ChatGPT and any MCP client.",
        "website": "https://tankoup.com",
        "source": REPO_URL,
    })


@mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
async def health(request: Request) -> Response:
    return JSONResponse({"status": "ok"})


@mcp.custom_route("/.well-known/openai-apps-challenge", methods=["GET"], include_in_schema=False)
async def openai_apps_challenge(request: Request) -> Response:
    if not settings.openai_apps_challenge:
        return PlainTextResponse("Not found", status_code=404)
    return PlainTextResponse(settings.openai_apps_challenge)


def client_ip(scope: Scope) -> str:
    """The caller's IP, for rate limiting.

    Cloud Run's front end appends the caller as the last X-Forwarded-For hop,
    after anything the caller sent, so a forged header changes nothing
    (checked in production: 125 requests with a different forged IP each were
    cut off at 120). mcp.tankoup.com points at Cloud Run directly, with no
    proxy in between that would put its own address there.
    """
    headers = dict(scope.get("headers", []))
    if b"x-forwarded-for" in headers:
        return headers[b"x-forwarded-for"].decode("latin-1").split(",")[-1].strip()
    client = scope.get("client")
    return client[0] if client else "unknown"


class RateLimit:
    """Fixed one-minute windows on /mcp, per client IP and for the whole instance.

    In memory, so each Cloud Run instance counts on its own; the service runs
    one instance at most, which makes these the real limits.
    """

    def __init__(self, app: ASGIApp, per_ip: int, global_: int):
        self.app = app
        self.per_ip = per_ip
        self.global_ = global_
        self.window = 0
        self.counts: defaultdict[str, int] = defaultdict(int)
        self.total = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/mcp") or scope["method"] == "OPTIONS":
            await self.app(scope, receive, send)
            return

        now = int(time.time())
        window = now // 60
        if window != self.window:
            self.window, self.total = window, 0
            self.counts.clear()
        ip = client_ip(scope)
        self.counts[ip] += 1
        self.total += 1
        if self.counts[ip] > self.per_ip or self.total > self.global_:
            retry_after = 60 - now % 60
            body = json.dumps({
                "jsonrpc": "2.0", "id": None,
                "error": {"code": -32000, "message": f"Rate limit exceeded. Retry in {retry_after} s."},
            }).encode()
            await send({"type": "http.response.start", "status": 429, "headers": [
                (b"content-type", b"application/json"),
                (b"retry-after", str(retry_after).encode()),
            ]})
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


def create_app() -> ASGIApp:
    security = (
        TransportSecuritySettings(allowed_hosts=settings.allowed_hosts, allowed_origins=[])
        if settings.allowed_hosts
        else TransportSecuritySettings(enable_dns_rebinding_protection=False)
    )
    # Stateless and plain JSON: every request stands alone, so any instance can
    # answer it and nothing is held between calls. These tools never ask the
    # client anything mid-call, so they lose nothing by it.
    app: ASGIApp = mcp.streamable_http_app(stateless_http=True, json_response=True, transport_security=security)
    app = RateLimit(app, per_ip=settings.rate_limit_per_ip, global_=settings.rate_limit_global)
    # Public, read-only data and no cookies: any web page may call it.
    return CORSMiddleware(
        app,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["Mcp-Session-Id", "Mcp-Protocol-Version"],
    )


app = create_app()
