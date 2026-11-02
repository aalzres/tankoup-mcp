FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN pip install --no-cache-dir uv==0.12.3

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-dev --frozen --no-install-project

COPY src/ ./src/
RUN uv sync --no-dev --frozen

RUN adduser --disabled-password --gecos "" appuser
USER appuser

EXPOSE 8080

ENV PATH="/app/.venv/bin:$PATH"
# PORT is set by Cloud Run. The rate limiter reads X-Forwarded-For itself;
# --proxy-headers only makes the app see https, so its links say https.
CMD ["sh", "-c", "uvicorn tankoup_mcp.app:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips=*"]
