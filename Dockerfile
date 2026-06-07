FROM python:3.14-slim

WORKDIR /app

RUN apt-get update && apt-get install -y git curl build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen

COPY . .
RUN mkdir -p data/memory data/skills data/security

ENV HELIX_ENV=production
ENV HELIX_REQUIRE_AUTH=true
ENV HELIX_GATEWAY_HOST=0.0.0.0
ENV HELIX_GATEWAY_PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/health || exit 1

CMD ["uv", "run", "helix", "gateway", "start", "--host", "0.0.0.0", "--port", "8000"]