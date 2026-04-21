# Security — RemoteVibeServer

This document describes the security model, threat mitigations, and best practices implemented in RemoteVibeServer.

## Secrets Handling

### Principle: No Secrets in the Repository

All credentials and API tokens are provided **exclusively** at deploy-time via the cloud-init user-data. The repository contains only:

- **Example files** with clearly marked `<PLACEHOLDER>` values
- **Scripts** that read secrets from the runtime environment file

### Runtime Secret Storage

| Artifact                        | Path                                   | Permissions | Owner  |
|---------------------------------|----------------------------------------|:-----------:|:------:|
| Environment / secrets file      | `/etc/dev-server/env`                  | `0600`      | `root` |
| Coder admin API token           | `/etc/dev-server/coder-admin-token`    | `0644`      | `root` |
| Agent environment profile       | `/etc/profile.d/agent-env.sh`          | `0644`      | `root` |
| Deployment status               | `/etc/dev-server/status`               | `0644`      | `root` |
| Provisioning log                | `/var/log/dev-server-provision.log`    | `0644`      | `root` |

The environment file is:
- Written by cloud-init before any script executes
- Readable only by root (mode `0600`)
- Never exposed over the network
- Never logged or printed by any script

### Secret Lifecycle

```
Cloud Provider Console / API
        │
        ▼
  cloud-init user-data  ──►  /etc/dev-server/env  (0600 root:root)
        │                            │
        │                            ├──► bootstrap.sh (source)
        │                            ├──► setup.sh     (source)
        │                            └──► systemd EnvironmentFile
        │
        ╳  Secrets never written to stdout, logs, or /tmp
```

## API Token Management

### Cloudflare API Token

- Must be a **scoped API token** (not a Global API Key)
- Required permissions: `Zone → DNS → Edit` for the target zone only
- The token is used once during provisioning to create/update the DNS A record
- It remains in the env file for potential re-runs but is never exposed

**Best practice:** Create a dedicated API token in the Cloudflare dashboard → My Profile → API Tokens → Create Token → Edit zone DNS.

### AI Agent API Keys

| Key                     | Used By             | Scope                         |
|-------------------------|---------------------|-------------------------------|
| `GITHUB_TOKEN`          | Copilot CLI, Codex  | `read:user`, `copilot`        |
| `ANTHROPIC_API_KEY`     | Claude Code CLI     | API access                    |
| `GOOGLE_API_KEY`        | Gemini CLI          | Generative AI API             |
| `OPENAI_API_KEY`        | Codex CLI, OpenCode | OpenAI API access             |
| `CODEX_OPENAI_AUTH_CODE`| Codex CLI           | OpenAI OAuth (ChatGPT plan)   |

- Keys are loaded into the shell environment via `/etc/profile.d/*.sh` scripts
- Each profile script reads from the env file — it does **not** hardcode values
- If an agent is disabled (`ENABLE_AGENT_*=false`), its key is ignored entirely

## HTTPS & Certificates

### Automatic TLS via Caddy

Caddy handles the entire TLS lifecycle:

1. **Certificate issuance** — via Let's Encrypt ACME HTTP-01 challenge
2. **Certificate renewal** — automatic, ~30 days before expiry
3. **Certificate storage** — Caddy's data directory (`/var/lib/caddy/`)
4. **Protocol** — TLS 1.2+ (TLS 1.3 preferred)

### Security Headers

The Caddyfile injects the following headers on every response:

| Header                        | Value                                        |
|-------------------------------|----------------------------------------------|
| `Strict-Transport-Security`   | `max-age=63072000; includeSubDomains; preload` |
| `X-Content-Type-Options`      | `nosniff`                                    |
| `X-Frame-Options`             | `SAMEORIGIN`                                 |
| `Referrer-Policy`             | `strict-origin-when-cross-origin`            |
| `Server`                      | *(removed)*                                  |

### Why Not Certbot + Nginx?

| Aspect           | Caddy (chosen)           | Certbot + Nginx              |
|------------------|:------------------------:|:----------------------------:|
| Certificate mgmt | Fully automatic          | Cron job + hooks             |
| Renewal failures | Self-healing             | Silent failure risk          |
| Config lines     | ~20                      | ~60+                         |
| WebSocket config | Automatic                | Manual `proxy_pass` config   |

## Network Security

### Firewall (UFW)

```
Default incoming:  DENY
Default outgoing:  ALLOW
Port 22/tcp:       ALLOW  (SSH)
Port 80/tcp:       ALLOW  (HTTP → HTTPS redirect)
Port 443/tcp:      ALLOW  (HTTPS)
```

All other inbound traffic is silently dropped. Coder listens on `127.0.0.1:3000` and is **never** directly accessible from the internet.

### Brute-Force Protection (fail2ban)

fail2ban is enabled with default settings to protect SSH:
- Monitors `/var/log/auth.log`
- Bans IPs after 5 failed login attempts
- Ban duration: 10 minutes (progressive)

### SSH Hardening (Recommended)

The provisioning scripts do not modify SSH configuration to avoid locking out the operator. However, we strongly recommend:

```bash
# /etc/ssh/sshd_config additions
PermitRootLogin prohibit-password
PasswordAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
```

## Docker Security

- Docker is installed from the **official Docker repository** (not distro packages)
- The workspace image uses `codercom/enterprise-base` which runs as a non-root user
  (`coder`, uid 1000) inside the container
- **Workspace containers run with `privileged: true`** so that `dockerd` can be
  started inside them when the user opts into the `docker` dev-tool.  This is a
  conscious trade-off: dockerd requires `CAP_SYS_ADMIN` / `CAP_NET_ADMIN`, which
  are not in the default container bounding set.  The security boundary is
  therefore the **workspace owner** — anyone with workspace access effectively
  has root on the host.  Only grant Coder workspaces to trusted users.
- If you do not need Docker inside workspaces, deselect it in the configurator;
  a future release may also expose a non-privileged template variant.

## Audit & Observability

| Log                                     | Contents                           |
|-----------------------------------------|------------------------------------|
| `/var/log/dev-server-provision.log`     | Full provisioning output           |
| `/var/log/caddy/access.log`            | HTTPS access logs (rotated)        |
| `journalctl -u coder`                  | Coder server logs                  |
| `journalctl -u caddy`                  | Caddy proxy logs                   |
| `/var/log/auth.log`                    | SSH authentication (fail2ban)      |

## Threat Model Summary

| Threat                              | Mitigation                                           |
|-------------------------------------|------------------------------------------------------|
| Secrets in source control           | All secrets injected via cloud-init at deploy-time   |
| Unencrypted traffic                 | Caddy enforces HTTPS with HSTS                       |
| SSH brute-force                     | fail2ban + key-only auth (recommended)               |
| Unauthorized port access            | UFW denies all except 22, 80, 443                    |
| Certificate expiry                  | Caddy auto-renews certificates                       |
| Env file exposure                   | Mode 0600, root-only access                          |
| Compromised workspace container     | Workspace owner is fully trusted; container runs `privileged: true` for Docker support — only grant to trusted users |
