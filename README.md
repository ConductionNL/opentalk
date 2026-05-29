# OpenTalk ExApp for Nextcloud

Nextcloud ExApp (External Application) that integrates [OpenTalk](https://opentalk.eu/) video conferencing.

## About This App

This is a **Nextcloud ExApp** that packages the OpenTalk video conferencing controller as a containerized application managed by Nextcloud's AppAPI. When you install this app, Nextcloud will automatically deploy and manage the OpenTalk container.

**For OpenTalk documentation, see:** https://docs.opentalk.eu/

## What is OpenTalk?

OpenTalk is a secure, open-source video conferencing solution developed in Germany with a focus on data protection and GDPR compliance. It provides:

- Secure video and audio conferencing
- Screen sharing and collaborative features
- End-to-end encryption options
- OIDC/Keycloak authentication integration

## What This App Does

- Packages OpenTalk controller as a Nextcloud ExApp
- Nextcloud automatically manages the container lifecycle
- Provides video conferencing directly within Nextcloud
- Integrates with Nextcloud's AppAPI for seamless deployment

## Requirements

- Nextcloud 30 or higher
- AppAPI app installed and configured with a deploy daemon
- Docker environment for ExApp containers

### External Dependencies

OpenTalk requires additional services for full functionality:

| Service | Purpose | Required |
|---------|---------|----------|
| PostgreSQL | Database | Yes |
| Redis | Caching | Yes |
| Keycloak | Authentication (OIDC) | Yes |
| LiveKit | WebRTC media server | Yes |
| RabbitMQ | Message broker | Optional |

## Installation

### Via Nextcloud App Store

1. Ensure AppAPI is installed and configured
2. Search for "OpenTalk" in the Nextcloud app store
3. Click Install - Nextcloud will pull and start the container

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

Configure via Nextcloud Admin Settings or environment variables:

| Variable | Description |
|----------|-------------|
| `OPENTALK_CTRL_DATABASE__URL` | PostgreSQL connection string |
| `OPENTALK_CTRL_OIDC__AUTHORITY` | Keycloak OIDC provider URL |
| `OPENTALK_CTRL_LIVEKIT__SERVICE_URL` | LiveKit WebRTC server URL |
| `OPENTALK_CTRL_LIVEKIT__API_KEY` | LiveKit API key |
| `OPENTALK_CTRL_LIVEKIT__API_SECRET` | LiveKit API secret |

## Development

### Building the Docker Image

```bash
# Build locally
make build

# Push to registry
make push

# Test locally
make test
```

### Project Structure

```
opentalk/
├── appinfo/
│   └── info.xml          # ExApp manifest
├── ex_app/
│   └── lib/
│       └── main.py       # FastAPI wrapper for AppAPI
├── Dockerfile            # Container definition
├── entrypoint.sh         # Container startup
├── requirements.txt      # Python dependencies
└── Makefile              # Build automation
```

## Architecture

This ExApp uses a FastAPI wrapper that:

1. Implements AppAPI lifecycle endpoints (`/heartbeat`, `/init`, `/enabled`)
2. Starts and manages the OpenTalk controller process
3. Proxies requests to the OpenTalk controller
4. Reports health status back to Nextcloud

## Related Projects

| Project | Description | Links |
|---------|-------------|-------|
| **OpenTalk** | Video conferencing platform | [Website](https://opentalk.eu/) / [Docs](https://docs.opentalk.eu/) / [GitLab](https://gitlab.opencode.de/opentalk) |
| **Nextcloud AppAPI** | External app framework | [GitHub](https://github.com/nextcloud/app_api) / [Docs](https://docs.nextcloud.com/server/latest/developer_manual/exapp_development/) |
| **Open Register** | Nextcloud register management | [Codeberg](https://codeberg.org/Conduction/openregister) |

## License

AGPL-3.0 - See [LICENSE](LICENSE) for details.

## Author

[Conduction B.V.](https://conduction.nl) - info@conduction.nl
