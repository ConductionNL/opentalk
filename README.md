# OpenTalk for Nextcloud

Nextcloud integration app for [OpenTalk](https://opentalk.eu/) video conferencing.

## About This App

This is a **Nextcloud wrapper app** that provides integration between Nextcloud and an external OpenTalk server. It does not contain the OpenTalk video conferencing platform itself - it connects your Nextcloud instance to a running OpenTalk deployment.

**For OpenTalk server documentation, see:** https://docs.opentalk.eu/

## What This App Does

- Adds an OpenTalk entry to the Nextcloud navigation
- Provides a UI within Nextcloud for starting and joining video conferences
- Integrates OpenTalk authentication with Nextcloud users
- Allows inviting Nextcloud users to OpenTalk conferences

## Requirements

- Nextcloud 28 or higher
- PHP 8.0 or higher
- A running [OpenTalk server](https://opentalk.eu/) instance

## Installation

### From the Nextcloud App Store

Search for "OpenTalk" in your Nextcloud app store and click Install.

### Manual Installation

1. Download the latest release from [GitHub Releases](https://github.com/ConductionNL/opentalk/releases)
2. Extract to your Nextcloud `apps` or `custom_apps` directory
3. Enable the app: `occ app:enable opentalk`

## Configuration

After installation, configure the OpenTalk server URL in the Nextcloud admin settings.

## Development

```bash
# Install dependencies
composer install
npm install

# Build frontend
npm run build

# Watch for changes
npm run watch

# Run linting
composer phpcs
npm run lint
```

## Related Projects

| Project | Description | Links |
|---------|-------------|-------|
| **OpenTalk** | Video conferencing platform | [Website](https://opentalk.eu/) / [Docs](https://docs.opentalk.eu/) / [GitLab](https://gitlab.opencode.de/opentalk) |
| **Open Register** | Nextcloud register management | [GitHub](https://github.com/ConductionNL/openregister) |

## License

AGPL-3.0 - See [LICENSE](LICENSE) for details.

## Author

[Conduction B.V.](https://conduction.nl) - info@conduction.nl
