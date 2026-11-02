"""Settings, all from environment variables."""

import os
from dataclasses import dataclass, field


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _list(name: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    # TankoUp API. The key travels as X-API-Key and never leaves the server.
    api_url: str = field(default_factory=lambda: os.environ.get("TANKOUP_API_URL", "https://api.tankoup.com").rstrip("/"))
    api_key: str = field(default_factory=lambda: os.environ.get("TANKOUP_API_KEY", ""))
    api_timeout_s: float = 15.0

    # Answers are cached in memory. Prices change when the API ingests the
    # MITECO feed, every 4 hours, so a few minutes of staleness is free.
    cache_ttl_s: int = field(default_factory=lambda: _int("CACHE_TTL_S", 600))
    cache_max_entries: int = 2_000

    # Requests to /mcp per client IP and per instance, per minute. Claude and
    # ChatGPT call from their own servers, so one IP can carry many users.
    rate_limit_per_ip: int = field(default_factory=lambda: _int("RATE_LIMIT_PER_IP", 120))
    rate_limit_global: int = field(default_factory=lambda: _int("RATE_LIMIT_GLOBAL", 600))
    # Route searches cost a Google Routes call upstream; a day's cap per instance.
    route_daily_limit: int = field(default_factory=lambda: _int("ROUTE_DAILY_LIMIT", 100))

    # Host header allowlist. Empty turns DNS-rebinding protection off, which is
    # right behind Cloud Run: its front end only routes the service's own hosts.
    allowed_hosts: list[str] = field(default_factory=lambda: _list("ALLOWED_HOSTS"))

    # Token for ChatGPT's domain verification, served at
    # /.well-known/openai-apps-challenge once a submission asks for one.
    openai_apps_challenge: str = field(default_factory=lambda: os.environ.get("OPENAI_APPS_CHALLENGE", ""))


settings = Settings()
