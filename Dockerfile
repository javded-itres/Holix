FROM python:3.14-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    build-essential \
    ffmpeg \
    ca-certificates \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libxshmfence1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --extra all

COPY . .

RUN mkdir -p data/memory data/skills data/security \
    && uv run playwright install chromium

ENV HOLIX_HOME=/data/.holix
ENV HOLIX_ENV=production
ENV HOLIX_REQUIRE_AUTH=true
ENV HOLIX_GATEWAY_HOST=0.0.0.0
ENV HOLIX_GATEWAY_PORT=8000
ENV HOLIX_TELEGRAM_ACCESS_REQUESTS=true
ENV HOLIX_TELEGRAM_VOICE_ENABLED=true
ENV HOLIX_TELEGRAM_FILES_ENABLED=true
ENV ENABLE_BROWSER_TOOLS=true
ENV BROWSER_HEADLESS=true

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f "http://127.0.0.1:${HOLIX_GATEWAY_PORT:-8000}/health" || exit 1

COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

VOLUME ["/data/.holix"]

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["gateway"]