# RemoteVibeServer

Fully automated, secure, self-hosted remote development environment — deployable via a single cloud-init file.

## Quick Start

See [`dev-server-provision/README.md`](dev-server-provision/README.md) for the complete documentation, architecture, and deployment guide.

## What's Inside

- **Interactive configurator** — cross-platform CLI to generate cloud-init configs
- **Automated provisioning** via cloud-init (no manual SSH)
- **Coder v2** for VS Code Web + Desktop Remote access
- **Caddy** reverse proxy with automatic HTTPS (Let's Encrypt)
- **Cloudflare DNS** automation via API
- **Optional AI agents** (Copilot, Claude, Gemini, OpenCode) — toggle via env flags
- **Security hardened** — UFW, fail2ban, HSTS, secrets-free repo

## Documentation

- [Interactive Configurator](dev-server-provision/configurator/README.md)
- [Architecture & Design Decisions](dev-server-provision/docs/architecture.md)
- [Security Model](dev-server-provision/docs/security.md)
- [Deployment Guide](dev-server-provision/docs/deployment.md)
- [Infrastructure Modules](dev-server-provision/infra/README.md)