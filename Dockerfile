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

# Stage 1: Build Python dependencies
FROM python:3.11-slim AS python-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/python-packages -r requirements.txt

# Stage 2: Get OpenTalk controller from upstream image
FROM registry.opencode.de/opentalk/controller:v0.31.0-3 AS opentalk-base

# Stage 3: Production image
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

# Copy Python dependencies from builder
COPY --from=python-builder /python-packages/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=python-builder /python-packages/bin/ /usr/local/bin/

# Set up ExApp wrapper
WORKDIR /app
COPY ex_app/ ex_app/
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Create config and data directories
RUN mkdir -p /etc/opentalk /var/lib/opentalk

# Environment variables (set by AppAPI)
ENV APP_ID=opentalk
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

# Expose ports: 23000 for AppAPI, 11311 for OpenTalk controller
EXPOSE 23000 11311

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -s http://localhost:${APP_PORT:-23000}/heartbeat | grep -q status || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "./entrypoint.sh"]
