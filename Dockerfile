# OpenTalk ExApp for Nextcloud
# Wraps OpenTalk video conferencing with AppAPI integration
#
# OpenTalk is a secure video conferencing solution that requires:
# - PostgreSQL database
# - Redis cache
# - Keycloak for authentication
# - LiveKit for WebRTC media
#
# See: https://docs.opentalk.eu/

FROM python:3.11-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies for ExApp wrapper
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/app/deps -r requirements.txt

# Get OpenTalk controller from upstream image
FROM registry.opencode.de/opentalk/controller:v0.31.0-3 AS opentalk-base

# Production image
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tini \
    libpq5 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy OpenTalk controller binary from upstream
COPY --from=opentalk-base /controller/opentalk-controller /usr/local/bin/opentalk-controller

# Copy Python dependencies
COPY --from=builder /app/deps /usr/local/lib/python3.11/site-packages

# Set up ExApp wrapper
WORKDIR /app
COPY ex_app /app/ex_app
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create config and data directories
RUN mkdir -p /etc/opentalk /var/lib/opentalk
COPY controller.toml /etc/opentalk/controller.toml

# Environment variables (set by AppAPI)
ENV APP_HOST=0.0.0.0
ENV APP_PORT=23000
ENV PYTHONUNBUFFERED=1

# OpenTalk configuration
ENV OPENTALK_PORT=11311
ENV OPENTALK_CTRL_HTTP__PORT=11311

# Database configuration (required)
ENV OPENTALK_CTRL_DATABASE__URL=postgres://opentalk:opentalk@localhost:5432/opentalk

# Redis configuration (required)
ENV OPENTALK_CTRL_REDIS__URL=redis://localhost:6379/

# Keycloak/OIDC configuration (required)
ENV OPENTALK_CTRL_OIDC__AUTHORITY=http://localhost:8081/realms/opentalk

# LiveKit configuration (required for video)
ENV OPENTALK_CTRL_LIVEKIT__SERVICE_URL=http://localhost:7880
ENV OPENTALK_CTRL_LIVEKIT__API_KEY=devkey
ENV OPENTALK_CTRL_LIVEKIT__API_SECRET=secret

# Expose ports: 9000 for AppAPI, 11311 for OpenTalk controller
EXPOSE 9000 11311

# Health check - just verify the wrapper is responding (any status is ok during init)
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -s http://localhost:${APP_PORT:-9000}/heartbeat | grep -q status || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
