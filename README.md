<p align="center">
  <img src="img/app.svg" alt="OpenTalk logo" width="80" height="80">
</p>

<h1 align="center">OpenTalk</h1>

<p align="center">
  <strong>GDPR-compliant video conferencing for Nextcloud — secure meetings, screen sharing, and end-to-end encryption via the Nextcloud AppAPI</strong>
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
- Reports health status back to Nextcloud

This app does **not** modify or extend the OpenTalk platform itself. It only provides the integration layer between Nextcloud and the upstream OpenTalk controller.

## Requirements

| Dependency | Version | Notes |
|-----------|---------|-------|
| Nextcloud | 30 -- 33 | |
| [AppAPI](https://apps.nextcloud.com/apps/app_api) | latest | Must be installed and configured with a deploy daemon |
| Docker | -- | Required for ExApp container deployment |
| PostgreSQL | 14+ | OpenTalk database backend |
| Redis | 6+ | Caching and session management |
| Keycloak | 20+ | OIDC authentication provider |
| LiveKit | 1.x | WebRTC media server for video/audio |
| RabbitMQ | 3.x | Message broker (optional) |

## Installation

### Via Nextcloud App Store

1. Ensure **AppAPI** is installed and configured with a deploy daemon
2. Search for **OpenTalk** in the Nextcloud External Apps section
3. Click **Install** -- Nextcloud will pull and start the container automatically

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
| `OPENTALK_CTRL_OIDC__AUTHORITY` | Keycloak OIDC provider URL (e.g., `http://keycloak:8080/realms/opentalk`) |
| `OPENTALK_CTRL_LIVEKIT__SERVICE_URL` | LiveKit WebRTC server URL |
| `OPENTALK_CTRL_LIVEKIT__API_KEY` | LiveKit API key |
| `OPENTALK_CTRL_LIVEKIT__API_SECRET` | LiveKit API secret |

### Keycloak Integration

| Variable | Description |
|----------|-------------|
| `KEYCLOAK_URL` | Keycloak server URL (e.g., `http://keycloak:8080`) |
| `KEYCLOAK_REALM` | Keycloak realm name (default: `commonground`) |
| `KEYCLOAK_CLIENT_ID` | OIDC client ID (default: `opentalk`) |
| `KEYCLOAK_CLIENT_SECRET` | OIDC client secret |

## Architecture

```
+-----------------------------------------+
|        Nextcloud + AppAPI               |
+-------------------+---------------------+
                    | AUTHORIZATION-APP-API
                    v
+-----------------------------------------+
|   OpenTalk ExApp Container              |
|  +-----------------------------------+  |
|  | FastAPI Wrapper (port 9000)       |  |
|  | - /heartbeat   (health check)     |  |
|  | - /init        (initialization)   |  |
|  | - /enabled     (enable/disable)   |  |
|  | - /*           (proxy to ctrl)    |  |
|  +----------------+------------------+  |
|                   |                     |
|  +----------------v------------------+  |
|  | OpenTalk Controller (port 11311)  |  |
|  | (upstream binary from             |  |
|  |  registry.opencode.de/opentalk)   |  |
|  +-----------------------------------+  |
+-----------------------------------------+
         |          |          |
    PostgreSQL    Redis    Keycloak   LiveKit
```

The FastAPI wrapper (`ex_app/lib/main.py`) handles the AppAPI contract:

1. **`/init`** -- Starts the OpenTalk controller process and waits for it to become healthy (up to 90 seconds)
2. **`/enabled`** -- Starts or stops the controller based on the enabled state
3. **`/heartbeat`** -- Checks controller health by probing `http://localhost:11311/v1/`
4. **`/*`** -- Proxies all other requests to the OpenTalk controller

## Links

| Resource | URL |
|----------|-----|
| OpenTalk Website | [opentalk.eu](https://opentalk.eu/) |
| OpenTalk Documentation | [docs.opentalk.eu](https://docs.opentalk.eu/) |
| OpenTalk Source Code | [gitlab.opencode.de/opentalk/controller](https://gitlab.opencode.de/opentalk/controller) |
| OpenTalk GmbH (Support & Licensing) | [opentalk.eu](https://opentalk.eu/) |
| This Wrapper (GitHub) | [ConductionNL/opentalk](https://github.com/ConductionNL/opentalk) |
| Nextcloud AppAPI | [GitHub](https://github.com/nextcloud/app_api) / [Docs](https://docs.nextcloud.com/server/latest/developer_manual/exapp_development/) |

## License

EUPL-1.2 -- See [LICENSE](LICENSE) for details.

This license applies to the **Nextcloud ExApp wrapper only**. The upstream OpenTalk controller is licensed separately under its own terms. See the [OpenTalk project](https://gitlab.opencode.de/opentalk/controller) for upstream licensing.

## Authors

Nextcloud wrapper built by [Conduction B.V.](https://conduction.nl) -- open-source software for Dutch government and public sector organizations.

OpenTalk platform developed by [OpenTalk GmbH](https://opentalk.eu/) -- secure video conferencing made in Germany.
