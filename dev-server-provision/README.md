# RemoteVibeServer — Dev Server Provision

> Fully automated, secure, self-hosted remote development environment deployable via a single cloud-init file.

## Overview

RemoteVibeServer provisions a complete remote development server with:

- **[Coder v2](https://coder.com/)** — open-source remote development platform
- **VS Code Web** (`code-server`) — one click in the Coder dashboard, runs in the browser
- **VS Code Desktop Remote** access via SSH
- **Automatic DNS** via Cloudflare API
- **Automatic HTTPS** via Caddy + Let's Encrypt
- **Optional AI agents** — GitHub Copilot, Claude Code, Gemini, OpenCode
- **Security hardened** — UFW firewall, fail2ban, HSTS, zero secrets in repo

Everything is deployed with a single `cloud-init` file. No manual SSH provisioning required.

## Architecture

```
Internet ──► Caddy (:443, HTTPS) ──► Coder (:3000, localhost)
                                        │
                                   Docker Workspaces
                                   (dev containers)
```

See [docs/architecture.md](docs/architecture.md) for the full architecture diagram and design rationale.

## Quick Start

### 1. Clone & configure

```bash
git clone https://github.com/PhilippWu/RemoteVibeServer.git
cd RemoteVibeServer/dev-server-provision
cp cloud-init.example.yaml cloud-init.yaml
```

Edit `cloud-init.yaml` and replace all `<PLACEHOLDER>` values with your actual credentials.

### 2. Deploy

```bash
# Hetzner Cloud
hcloud server create \
  --name dev-server \
  --type cpx31 \
  --image ubuntu-24.04 \
  --ssh-key my-key \
  --user-data-from-file cloud-init.yaml
```

### 3. Access

After ~5 minutes, open `https://<SUBDOMAIN>.<DOMAIN>` in your browser to access Coder.

For VS Code Desktop Remote:
```bash
coder login https://<SUBDOMAIN>.<DOMAIN>
coder config-ssh
# Then: VS Code → Remote-SSH → coder.<workspace>
```

See [docs/deployment.md](docs/deployment.md) for the full step-by-step guide.

## Interactive Configurator

Instead of manually editing `cloud-init.yaml`, use the interactive configurator:

```bash
cd dev-server-provision/configurator
pip install -r requirements.txt
python -m configurator
```

The configurator provides a guided CLI that walks you through provider selection, domain setup, Cloudflare configuration, AI agent selection with API key entry, and preflight validation — then generates a ready-to-use `cloud-init.yaml` and optionally deploys via `hcloud`.

See [configurator/README.md](configurator/README.md) for full documentation.

## Repository Structure

```
dev-server-provision/
├── cloud-init.example.yaml   # Cloud-init template (THE entry-point)
├── bootstrap.sh              # Thin bootstrap — loads env, downloads scripts
├── setup.sh                  # Main orchestration script
├── configurator/             # Interactive CLI configurator (cross-platform)
│   ├── cli.py                # Main interactive flow
│   ├── generator.py          # cloud-init YAML generation
│   ├── providers.py          # Cloud provider definitions
│   ├── validators.py         # Input validation & preflight checks
│   ├── requirements.txt      # Python dependencies
│   └── README.md             # Configurator documentation
├── infra/
│   ├── dns.sh                # Cloudflare DNS A-record automation
│   ├── proxy.sh              # Caddy reverse proxy + auto HTTPS
│   ├── agents.sh             # Optional AI coding agent installation
│   └── README.md             # Module documentation
├── coder/
│   ├── main.tf               # Terraform template (Docker container + volumes + coder_app)
│   ├── Dockerfile            # Default workspace image (code-server, AI agents, dev tools)
│   └── devcontainer.json     # Dev container configuration
├── docs/
│   ├── architecture.md       # Architecture & design decisions
│   ├── security.md           # Security model & threat mitigations
│   └── deployment.md         # Step-by-step deployment guide
└── README.md                 # This file
```

## Environment Variables

All configuration is provided via the environment file written by cloud-init to `/etc/dev-server/env`.

### Required

| Variable                | Description                           |
|-------------------------|---------------------------------------|
| `DOMAIN`                | Root domain (e.g., `example.com`)     |
| `SUBDOMAIN`             | Subdomain (e.g., `dev`)              |
| `EMAIL`                 | Email for Let's Encrypt & alerts     |
| `CLOUDFLARE_API_TOKEN`  | Scoped API token (Zone:DNS:Edit)     |
| `CLOUDFLARE_ZONE_ID`    | Cloudflare zone identifier           |

### Optional

| Variable                | Default  | Description                                      |
|-------------------------|----------|--------------------------------------------------|
| `CODER_URL`             | auto     | Coder access URL                                 |
| `CODER_ADMIN_PASSWORD`  | auto     | Coder admin password (≥8 chars, no spaces). Auto-generated if omitted. |
| `ENABLE_AGENT_COPILOT`  | `false`  | Install GitHub Copilot CLI in workspaces         |
| `ENABLE_AGENT_CLAUDE`   | `false`  | Install Anthropic Claude Code in workspaces      |
| `ENABLE_AGENT_GEMINI`   | `false`  | Install Google Gemini CLI in workspaces          |
| `ENABLE_AGENT_OPENCODE` | `false`  | Install OpenCode AI coding agent in workspaces   |
| `OPENAI_API_KEY`        | *(empty)*| OpenAI API key                                   |
| `ANTHROPIC_API_KEY`     | *(empty)*| Anthropic API key                                |
| `GOOGLE_API_KEY`        | *(empty)*| Google AI API key                                |
| `GITHUB_TOKEN`          | *(empty)*| GitHub token for Copilot CLI + gh                |
| `FORCE_DOWNLOAD`        | `false`  | Re-download scripts on re-run                    |

## Security

- **Zero secrets in the repository** — all credentials injected via cloud-init
- **Environment file**: `/etc/dev-server/env` with mode `0600` (root-only)
- **Firewall**: UFW allows only ports 22, 80, 443
- **Brute-force protection**: fail2ban on SSH
- **HTTPS**: Caddy with automatic Let's Encrypt + HSTS
- **Coder**: Listens on `127.0.0.1:3000` only — never exposed directly

See [docs/security.md](docs/security.md) for the full security model and threat analysis.

## Platform Choice: Why Coder?

We evaluated three self-hosted remote development platforms:

| Feature                  | **Coder v2** ✅  | code-server       | VS Code Server     |
|--------------------------|:-----------------:|:-----------------:|:------------------:|
| VS Code Web              | ✅                | ✅                | ✅ (preview)       |
| VS Code Desktop Remote   | ✅ (SSH)          | ❌                | ✅                 |
| Extension marketplace    | ✅ Open VSX + MS  | ✅ Open VSX only  | ✅ Full MS         |
| Multi-user support       | ✅                | ❌                | ❌                 |
| Workspace templates      | ✅ (Docker/K8s)   | ❌                | ❌                 |
| Self-hosted OSS          | ✅ Apache 2.0     | ✅ MIT            | ⚠️ Proprietary     |
| Built-in auth            | ✅                | Basic             | ❌                 |

**Coder v2** provides the best balance of functionality, security, and extensibility. It supports both VS Code Web and Desktop Remote access, has a powerful template system for reproducible workspaces, and is fully open-source.

### Alternative Considerations

- **code-server**: Excellent for simple single-user setups, but lacks VS Code Desktop Remote and multi-user support.
- **VS Code Server (Microsoft)**: Good marketplace support, but proprietary licensing and limited self-hosting options.
- **Gitpod**: Cloud-native but heavier to self-host, more suited for Kubernetes environments.

## AI Agents

AI coding agents are **opt-in** and controlled via environment flags:

```yaml
ENABLE_AGENT_COPILOT=true    # GitHub Copilot CLI
ENABLE_AGENT_CLAUDE=true     # Anthropic Claude Code
ENABLE_AGENT_GEMINI=true     # Google Gemini CLI
ENABLE_AGENT_OPENCODE=true   # OpenCode AI coding agent
```

Each agent requires its corresponding API key. Missing keys cause a skip (not a failure).

## Troubleshooting

| Problem                          | Solution                                                    |
|----------------------------------|-------------------------------------------------------------|
| Provisioning stuck               | `ssh root@<ip>` → `tail -f /var/log/dev-server-provision.log` |
| DNS not resolving                | Re-run: `source /etc/dev-server/env && bash /opt/dev-server-provision/infra/dns.sh` |
| HTTPS certificate error          | Check: `journalctl -u caddy` — ensure port 80 is open       |
| Coder won't start                | Check: `journalctl -u coder` — ensure Docker is running     |
| Want to re-provision             | `FORCE_DOWNLOAD=true /etc/dev-server/bootstrap.sh`          |

## References

- [Coder Documentation](https://coder.com/docs)
- [Caddy Documentation](https://caddyserver.com/docs)
- [Cloudflare API v4](https://developers.cloudflare.com/api/)
- [cloud-init Documentation](https://cloudinit.readthedocs.io/)
- [Hetzner Cloud](https://docs.hetzner.com/cloud/)
- [Let's Encrypt](https://letsencrypt.org/docs/)

## License

This project is provided as-is for development and educational purposes.
