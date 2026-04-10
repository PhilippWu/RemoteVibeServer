# Infrastructure Modules

This directory contains modular shell scripts that handle individual aspects of the server provisioning. Each script is designed to be:

- **Idempotent** — safe to run multiple times without side effects
- **Self-contained** — depends only on the shared environment file
- **Logged** — all actions are written to `/var/log/dev-server-provision.log`

## Module Overview

| Script      | Purpose                                    | Key Dependencies        |
|-------------|--------------------------------------------|------------------------|
| `dns.sh`    | Cloudflare DNS A-record automation         | `curl`, `jq`, `dig`   |
| `proxy.sh`  | Caddy reverse proxy with automatic HTTPS   | `caddy`                |
| `agents.sh` | Optional AI coding agent installation      | `node`, `npm`          |

## dns.sh

Creates or updates an A record in Cloudflare pointing the configured FQDN to the server's public IP.

**Environment variables required:**
- `CLOUDFLARE_API_TOKEN` — API token with `Zone:DNS:Edit` permission
- `CLOUDFLARE_ZONE_ID` — Cloudflare zone identifier
- `SUBDOMAIN`, `DOMAIN` — used to construct the FQDN
- `PUBLIC_IP` — detected by `setup.sh`

**Behavior:**
1. Queries existing A records for the FQDN
2. If a record exists with the correct IP → no-op
3. If a record exists with a different IP → updates it
4. If no record exists → creates one
5. Waits up to 60 s for DNS propagation via Cloudflare's resolver (1.1.1.1)

## proxy.sh

Installs and configures [Caddy](https://caddyserver.com/) as a reverse proxy in front of Coder on `127.0.0.1:3000`.

**Why Caddy?**
- Automatic HTTPS via Let's Encrypt (ACME HTTP-01)
- Native WebSocket support (required for Coder terminals)
- Single binary, minimal attack surface
- No manual certificate management

**Environment variables required:**
- `FQDN` — domain to serve
- `EMAIL` — ACME registration email

## agents.sh

Optionally installs AI coding CLI tools. Each agent is controlled by a boolean flag and its corresponding API key.

| Flag                    | Key Required        | Agent                   |
|-------------------------|---------------------|-------------------------|
| `ENABLE_AGENT_COPILOT`  | `GITHUB_TOKEN`      | GitHub Copilot CLI      |
| `ENABLE_AGENT_CLAUDE`   | `ANTHROPIC_API_KEY` | Anthropic Claude Code   |
| `ENABLE_AGENT_GEMINI`   | `GOOGLE_API_KEY`    | Google Gemini CLI       |
| `ENABLE_AGENT_OPENCODE` | Any provider key¹   | OpenCode AI agent       |

¹ OpenCode supports multiple providers. At least one of `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GOOGLE_API_KEY` must be set.

If a flag is `true` but the corresponding key is empty, the agent is skipped with a warning.
