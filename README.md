<p align="center">
  <img src="img/app-store.svg" alt="OpenTalk logo" width="80" height="80">
</p>

<h1 align="center">OpenTalk</h1>

<p align="center">
  <strong>GDPR-compliant video conferencing for Nextcloud -- secure meetings, screen sharing, and end-to-end encryption via the Nextcloud AppAPI</strong>
</p>

<p align="center">
  <a href="https://github.com/ConductionNL/opentalk/releases"><img src="https://img.shields.io/github/v/release/ConductionNL/opentalk" alt="Latest release"></a>
  <a href="https://github.com/ConductionNL/opentalk/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-EUPL--1.2-blue" alt="License"></a>
</p>

---

> **IMPORTANT DISCLAIMER**
>
> This repository contains only a **Nextcloud ExApp wrapper** for [OpenTalk](https://opentalk.eu/), developed and maintained by [Conduction B.V.](https://conduction.nl). The wrapper packages the upstream OpenTalk controller as a containerized application managed by Nextcloud's AppAPI.
>
> **OpenTalk itself is developed by [OpenTalk GmbH](https://opentalk.eu/).**
>
> Conduction does **NOT** provide:
> - Support, SLAs, or guarantees for the OpenTalk platform
> - Licensing or pricing for OpenTalk
> - Bug fixes or feature development for the upstream OpenTalk controller
> - Any warranty regarding OpenTalk's functionality or fitness for purpose
>
> **For OpenTalk support, licensing, pricing, and services, contact [OpenTalk GmbH](https://opentalk.eu/) directly.**
>
> For issues specific to the **Nextcloud wrapper** (AppAPI integration, container lifecycle, proxy layer), you may open an issue on [this repository](https://github.com/ConductionNL/opentalk/issues).

## What is OpenTalk?

[OpenTalk](https://opentalk.eu/) is a secure, open-source video conferencing platform developed in Germany by [OpenTalk GmbH](https://opentalk.eu/) with a strong focus on data protection and GDPR compliance. It is designed as a sovereign alternative to commercial cloud-based video conferencing solutions, keeping all communication data under your own control.

Key capabilities of the OpenTalk platform:

- **Secure Video and Audio Conferencing** -- High-quality WebRTC-based meetings via LiveKit
- **Screen Sharing** -- Present your screen or individual application windows
- **End-to-End Encryption** -- Optional E2EE for maximum confidentiality
- **OIDC / Keycloak Authentication** -- Enterprise single sign-on integration
- **Moderation Tools** -- Meeting controls, waiting rooms, and participant management
- **Recording** -- Server-side meeting recording (when configured)
- **Data Sovereignty** -- Self-hosted, no data leaves your infrastructure

For full documentation, see [docs.opentalk.eu](https://docs.opentalk.eu/).

## What This App Does

This Nextcloud ExApp (External Application) wraps the upstream OpenTalk controller in a container that Nextcloud manages through the [AppAPI](https://github.com/nextcloud/app_api) framework. Specifically, this wrapper:

- Packages the OpenTalk controller binary from the official upstream image
- Implements AppAPI lifecycle endpoints (`/heartbeat`, `/init`, `/enabled`)
- Starts and manages the OpenTalk controller process inside the container
- Proxies all requests from Nextcloud to the OpenTalk controller
- Provides seamless **iframe-embedded** experience inside Nextcloud (no new tabs)
- Handles **automatic Keycloak SSO** via the Keycloak ExApp -- users are pre-authenticated without browser-side OIDC redirects
- Reports health status back to Nextcloud

<p align="center">
  <img src="docs/opentalk-iframe-nextcloud.png" alt="OpenTalk running inside Nextcloud as an embedded iframe" width="800">
  <br>
  <em>OpenTalk dashboard running seamlessly inside a Nextcloud iframe</em>
</p>

This app does **not** modify or extend the OpenTalk platform itself. It only provides the integration layer between Nextcloud and the upstream OpenTalk controller.

## Requirements

| Dependency | Version | Notes |
|-----------|---------|-------|
| Nextcloud | 30 -- 33 | |
| [AppAPI](https://apps.nextcloud.com/apps/app_api) | latest | Must be installed and configured with a deploy daemon |
| Docker | -- | Required for ExApp container deployment |
| PostgreSQL | 14+ | OpenTalk database backend |
| Redis | 6+ | Caching and session management |
| [Keycloak ExApp](https://github.com/ConductionNL/keycloak-nextcloud) | latest | Shared OIDC provider -- syncs Nextcloud users to Keycloak |
| LiveKit | 1.x | WebRTC media server for video/audio |

## Installation

### Via Nextcloud App Store

1. Ensure **AppAPI** is installed and configured with a deploy daemon
2. Install the **Keycloak ExApp** first (required for authentication)
3. Search for **OpenTalk** in the Nextcloud External Apps section
4. Click **Install** -- Nextcloud will pull and start the container automatically

### Manual Registration

```bash
# Register the ExApp with AppAPI
docker exec -u www-data nextcloud php occ app_api:app:register \
    opentalk your_daemon_name \
    --info-xml /path/to/appinfo/info.xml \
    --force-scopes

# Enable the ExApp
docker exec -u www-data nextcloud php occ app_api:app:enable opentalk
```

## Configuration

Configure via Nextcloud Admin Settings or container environment variables. All environment variables are defined in `appinfo/info.xml` and passed through by AppAPI.

### OpenTalk Controller

| Variable | Description |
|----------|-------------|
| `OPENTALK_CTRL_DATABASE__URL` | PostgreSQL connection string (e.g., `postgres://user:pass@host:5432/opentalk`) |
| `OPENTALK_CTRL_REDIS__URL` | Redis connection string (e.g., `redis://localhost:6379/`) |
| `OPENTALK_CTRL_OIDC__AUTHORITY` | Keycloak OIDC provider URL (auto-configured when using Keycloak ExApp) |
| `OPENTALK_CTRL_LIVEKIT__SERVICE_URL` | LiveKit WebRTC server URL |
| `OPENTALK_CTRL_LIVEKIT__API_KEY` | LiveKit API key |
| `OPENTALK_CTRL_LIVEKIT__API_SECRET` | LiveKit API secret |

### Keycloak Integration

| Variable | Description |
|----------|-------------|
| `KEYCLOAK_EXAPP_URL` | URL of the Keycloak ExApp container (e.g., `http://keycloak-container:23002`) |
| `KEYCLOAK_API_SECRET` | Shared secret for ExApp-to-ExApp auth (must match Keycloak ExApp) |
| `KEYCLOAK_REALM` | Keycloak realm name (default: `commonground`) |
| `KEYCLOAK_BROWSER_URL` | Browser-accessible Keycloak URL for OIDC config (default: `http://localhost:8180`) |

## Architecture

### Component Overview

The OpenTalk ExApp orchestrates seven components to deliver embedded video conferencing inside Nextcloud:

| Component | Image / Technology | Role | Port |
|-----------|-------------------|------|------|
| **FastAPI Wrapper** | Python / nc_py_api | AppAPI lifecycle, auth proxy, frontend serving | 23005 (ExApp) |
| **OpenTalk Controller** | `registry.opencode.de/opentalk/controller` | Meeting management, signaling, REST API | 11311 (internal) |
| **OpenTalk Frontend** | React SPA (bundled) | Meeting UI, dashboard, settings | Served by wrapper |
| **Keycloak ExApp** | `ghcr.io/conductionnl/keycloak-nextcloud` | OIDC identity provider, user sync from Nextcloud | 23002 (ExApp), 8080 (KC) |
| **LiveKit** | `livekit/livekit-server` | WebRTC SFU -- routes video/audio/screen streams between participants | 7880 (API), 7881 (WS) |
| **Redis** | `redis:7-alpine` | Session cache, pub/sub for controller events | 6379 |
| **MinIO** | `minio/minio` | S3-compatible object storage for file uploads and meeting assets | 9000 |
| **PostgreSQL** | Shared with Nextcloud | Persistent storage for meetings, users, recordings | 5432 |

### Infrastructure Diagram

```mermaid
graph TB
    subgraph "Browser"
        NC["Nextcloud UI"]
        IF["OpenTalk iframe"]
    end

    subgraph "Nextcloud Server"
        AA["AppAPI Proxy<br/><i>Adds CSP nonce + auth headers</i>"]
    end

    subgraph "OpenTalk ExApp Container"
        FW["FastAPI Wrapper<br/><i>Port 23005</i><br/>Auth proxy, frontend serving,<br/>AppAPI lifecycle"]
        OT["OpenTalk Controller<br/><i>Port 11311</i><br/>Meeting signaling, REST API,<br/>room management"]
        TCP["TCP Proxy<br/><i>localhost:8180 &rarr; keycloak:8080</i><br/>OIDC issuer URL consistency"]
        FE["OpenTalk Frontend<br/><i>React SPA</i><br/>Meeting UI, dashboard"]
    end

    subgraph "Supporting Services"
        KC["Keycloak ExApp<br/><i>Port 23002 / 8080</i><br/>OIDC provider, user sync,<br/>token API"]
        LK["LiveKit Server<br/><i>Port 7880 / 7881</i><br/>WebRTC SFU for<br/>video/audio streams"]
        RD["Redis<br/><i>Port 6379</i><br/>Session cache,<br/>pub/sub events"]
        MN["MinIO<br/><i>Port 9000</i><br/>Object storage for<br/>file uploads"]
        PG["PostgreSQL<br/><i>Port 5432</i><br/>Meetings, users,<br/>recordings"]
    end

    NC -->|"iframe src"| AA
    AA -->|"AUTHORIZATION-APP-API"| FW
    FW -->|"Serves static files"| FE
    FW -->|"Proxies /v1/* API calls"| OT
    FW -->|"GET /api/auth/token"| KC
    IF -->|"WebSocket wss://"| LK
    OT -->|"Room signaling"| LK
    OT -->|"Session data"| RD
    OT -->|"File uploads"| MN
    OT -->|"Meetings DB"| PG
    OT -->|"Token validation"| TCP
    TCP -->|"OIDC introspection"| KC
    KC -->|"Identity DB"| PG

    style FW fill:#4a9,stroke:#333,color:#fff
    style OT fill:#369,stroke:#333,color:#fff
    style KC fill:#c63,stroke:#333,color:#fff
    style LK fill:#96c,stroke:#333,color:#fff
    style RD fill:#d44,stroke:#333,color:#fff
    style MN fill:#e80,stroke:#333,color:#fff
    style PG fill:#36a,stroke:#333,color:#fff
```

### Component Details

#### FastAPI Wrapper (`ex_app/lib/main.py`)

The Python wrapper is the entry point for all Nextcloud communication. It implements the AppAPI contract and adds the authentication proxy layer.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/heartbeat` | GET | AppAPI health check -- probes the controller at `localhost:11311` |
| `/init` | POST | Starts controller, rewrites frontend paths, registers top menu |
| `/enabled` | PUT | Starts or stops the controller process |
| `/api/auth/token` | GET | Proxies token request to Keycloak ExApp (container-to-container) |
| `/config.js` | GET | Generates runtime frontend config (OIDC authority, base URL) |
| `/js/opentalk-iframe-loader.js` | GET | Iframe loader injected into the Nextcloud page |
| `/v1/*` | ALL | Proxied to the OpenTalk controller |
| `/*` | GET | Serves static frontend files (SPA fallback to `index.html`) |

#### OpenTalk Controller

The upstream [OpenTalk controller](https://gitlab.opencode.de/opentalk/controller) binary runs as a child process managed by the wrapper. It handles all meeting logic, WebRTC signaling via LiveKit, and exposes the REST API at port 11311.

Configuration lives in `controller.toml` with sections for:
- **`[database]`** -- PostgreSQL connection for meeting persistence
- **`[redis]`** -- Session cache and event pub/sub
- **`[oidc]`** -- Keycloak authority URL (overridden at runtime via TCP proxy)
- **`[oidc.frontend]`** -- Public OIDC client (`opentalk`) for browser flows
- **`[oidc.controller]`** -- Confidential OIDC client (`opentalk-controller`) for server-side token introspection
- **`[livekit]`** -- WebRTC media server connection (public + service URLs)
- **`[minio]`** -- S3 object storage for file uploads

#### LiveKit Server

[LiveKit](https://livekit.io/) is an open-source WebRTC Selective Forwarding Unit (SFU). It routes video, audio, and screen-sharing streams between meeting participants without mixing -- enabling low-latency, high-quality conferencing.

- **Port 7880** -- HTTP API used by the OpenTalk controller for room management
- **Port 7881** -- WebSocket endpoint where browser clients connect for media streams
- **Dev mode** (`--dev`) -- Runs with simplified config; API key `devkey` / secret `secret`

#### Redis

Shared Redis instance (`redis:7-alpine`) used by the OpenTalk controller for:
- Session caching and token storage
- Pub/sub event delivery between controller instances
- Also shared with other Common Ground ExApps (OpenZaak, OpenKlant)

#### MinIO

S3-compatible object storage (`minio/minio`) for OpenTalk file uploads and meeting assets (recordings, shared files). Accessible at `http://openregister-exapp-minio:9000` with default credentials `minioadmin/minioadmin`.

#### TCP Proxy (OIDC Issuer Consistency)

A lightweight TCP proxy thread inside the container forwards `localhost:8180` to `keycloak:8080`. This ensures the OIDC issuer URL (`http://localhost:8180/realms/commonground`) is identical in:
- Keycloak-issued JWT tokens (`iss` claim)
- The OpenTalk controller's OIDC authority configuration
- The browser's OIDC discovery endpoint

Without this proxy, issuer mismatches would cause token validation failures.

### Authentication Flow

The OpenTalk ExApp uses a **server-side token pre-loading** strategy to provide seamless SSO inside a Nextcloud iframe, bypassing browser-side OIDC redirects that CSP would block:

1. **User clicks OpenTalk** in the Nextcloud top menu
2. Nextcloud loads the **iframe loader script** which creates an iframe pointing to the ExApp
3. The ExApp serves `index.html` with an injected **bootstrap script** (CSP nonce-safe)
4. The bootstrap script calls **`/api/auth/token`** via synchronous XHR (same-origin, Nextcloud session cookie provides auth)
5. The token endpoint calls the **Keycloak ExApp** container-to-container with a shared secret
6. The Keycloak ExApp uses the **direct access grant** to get a Keycloak token for the Nextcloud user
7. Tokens (`access_token`, `refresh_token`, `id_token`) are stored in **localStorage** before the React app initializes
8. The bootstrap also calls **`POST /v1/auth/login`** on the OpenTalk controller for server-side session setup
9. When the React app starts, `hasActiveSession()` finds valid tokens and the user is immediately **authenticated**

```mermaid
sequenceDiagram
    participant B as Browser (iframe)
    participant NC as Nextcloud AppAPI
    participant FW as FastAPI Wrapper
    participant KC as Keycloak ExApp
    participant KS as Keycloak Server
    participant OT as OpenTalk Controller

    B->>NC: GET /proxy/opentalk/
    NC->>FW: GET / (+ auth headers)
    FW-->>NC: index.html + bootstrap script (nonce-safe)
    NC-->>B: HTML with CSP nonce

    Note over B: Bootstrap script runs (sync XHR)

    B->>NC: XHR GET /proxy/opentalk/api/auth/token
    NC->>FW: GET /api/auth/token (+ auth headers)
    FW->>KC: POST /api/token (X-API-SECRET, X-NC-USER-ID)
    KC->>KS: POST /token (grant_type=password)
    KS-->>KC: access_token, refresh_token, id_token
    KC-->>FW: tokens
    FW-->>NC: tokens
    NC-->>B: tokens

    Note over B: localStorage.setItem("access_token", ...)
    Note over B: localStorage.setItem("refresh_token", ...)
    Note over B: localStorage.setItem("id_token", ...)

    B->>NC: POST /proxy/opentalk/v1/auth/login {id_token}
    NC->>FW: POST /v1/auth/login
    FW->>OT: POST /v1/auth/login
    OT-->>FW: session created
    FW-->>NC: OK
    NC-->>B: OK

    Note over B: React app initializes
    Note over B: hasActiveSession() = true
    Note over B: Dashboard renders
```

### Key Design Decisions

- **Synchronous XHR** for the bootstrap (not async `fetch`) to ensure tokens are in localStorage before the React app's Redux store initializes
- **CSP nonce compliance**: Nextcloud's AppAPI proxy auto-adds nonce attributes to all `<script>` tags in proxied HTML, so inline bootstrap scripts are CSP-safe
- **TCP proxy** inside the container maps `localhost:8180` to the Keycloak container, ensuring the OIDC issuer URL in tokens matches what the OpenTalk controller expects
- **`controller.toml`** uses separate OIDC clients: `opentalk` (public, for frontend) and `opentalk-controller` (confidential, for server-side introspection)
- **Container-to-container auth** uses a shared secret (`KEYCLOAK_API_SECRET`) for the token API, bypassing AppAPI middleware on internal routes

## Links

| Resource | URL |
|----------|-----|
| OpenTalk Website | [opentalk.eu](https://opentalk.eu/) |
| OpenTalk Documentation | [docs.opentalk.eu](https://docs.opentalk.eu/) |
| OpenTalk Source Code | [gitlab.opencode.de/opentalk/controller](https://gitlab.opencode.de/opentalk/controller) |
| OpenTalk GmbH (Support & Licensing) | [opentalk.eu](https://opentalk.eu/) |
| This Wrapper (GitHub) | [ConductionNL/opentalk](https://github.com/ConductionNL/opentalk) |
| Keycloak ExApp | [ConductionNL/keycloak-nextcloud](https://github.com/ConductionNL/keycloak-nextcloud) |
| Nextcloud AppAPI | [GitHub](https://github.com/nextcloud/app_api) / [Docs](https://docs.nextcloud.com/server/latest/developer_manual/exapp_development/) |

## License

EUPL-1.2 -- See [LICENSE](LICENSE) for details.

This license applies to the **Nextcloud ExApp wrapper only**. The upstream OpenTalk controller is licensed separately under its own terms. See the [OpenTalk project](https://gitlab.opencode.de/opentalk/controller) for upstream licensing.

## Authors

Nextcloud wrapper built by [Conduction B.V.](https://conduction.nl) -- open-source software for Dutch government and public sector organizations.

OpenTalk platform developed by [OpenTalk GmbH](https://opentalk.eu/) -- secure video conferencing made in Germany.
