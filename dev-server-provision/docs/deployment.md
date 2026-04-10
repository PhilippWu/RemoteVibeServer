# Deployment Guide — RemoteVibeServer

This guide walks through deploying a fully automated remote development server from scratch.

## Prerequisites

1. **A cloud provider account** — Hetzner is recommended (affordable, EU-based, great API). Any provider supporting cloud-init works (AWS, GCP, Azure, DigitalOcean, etc.).

2. **A domain name** — with DNS managed by Cloudflare.

3. **A Cloudflare API token** — with `Zone → DNS → Edit` permission for your domain's zone.

4. **Server requirements:**
   - Ubuntu 24.04 LTS
   - Minimum: 2 vCPUs, 4 GB RAM, 40 GB SSD (Hetzner CPX21 or larger)
   - Recommended: 4 vCPUs, 8 GB RAM, 80 GB SSD (Hetzner CPX31)

## Step 1: Prepare the Cloud-Init File

1. Copy the example file:
   ```bash
   cp cloud-init.example.yaml cloud-init.yaml
   ```

2. Fill in **all** placeholders:

   | Placeholder                | Example Value                  | Description                          |
   |----------------------------|--------------------------------|--------------------------------------|
   | `<YOUR_DOMAIN>`            | `example.com`                  | Your root domain                     |
   | `<YOUR_SUBDOMAIN>`         | `dev`                          | Subdomain for the dev server         |
   | `<YOUR_EMAIL>`             | `admin@example.com`            | Email for Let's Encrypt & alerts     |
   | `<YOUR_CLOUDFLARE_API_TOKEN>` | `cf_abc123...`             | Scoped Cloudflare API token          |
   | `<YOUR_CLOUDFLARE_ZONE_ID>`| `zone_xyz789...`               | Cloudflare zone ID for your domain   |
   | `<YOUR_ADMIN_PASSWORD>`    | `MySecurePass1`                | Coder admin password (≥8 chars, no spaces). Omit to auto-generate. |

3. Optionally enable AI agents:
   ```yaml
   ENABLE_AGENT_COPILOT=true
   ENABLE_AGENT_CLAUDE=true
   ENABLE_AGENT_CODEX=true
   ENABLE_AGENT_OPENCODE=true
   GITHUB_TOKEN=ghp_xxxx
   ANTHROPIC_API_KEY=sk-ant-xxxx
   OPENAI_API_KEY=sk-xxxx
   OPENCODE_PROVIDER=opencode-zen
   ```

> ⚠️ **NEVER** commit `cloud-init.yaml` (the filled-in version) to Git.

## Step 2: Create the Server

### Hetzner Cloud (CLI)

```bash
# Install hcloud CLI
brew install hcloud  # macOS
# or: apt install hcloud-cli  # Ubuntu

# Create the server
hcloud server create \
  --name dev-server \
  --type cpx31 \
  --image ubuntu-24.04 \
  --location nbg1 \
  --ssh-key your-ssh-key-name \
  --user-data-from-file cloud-init.yaml
```

### Hetzner Cloud (Web Console)

1. Go to https://console.hetzner.cloud
2. Create new server → Ubuntu 24.04
3. Choose CPX31 (or larger)
4. Under **Cloud config**, paste the contents of your `cloud-init.yaml`
5. Add your SSH key
6. Create server

### Other Providers

- **AWS**: Use the `UserData` field in EC2 launch configuration
- **GCP**: Use `metadata.user-data` with `cloud-init` compatible images
- **DigitalOcean**: Paste into the "User data" field when creating a droplet

### Alternative: Bare-Server Install (no cloud-init)

If your server does **not** support cloud-init (e.g. a dedicated/bare-metal
machine), use the one-liner installer instead:

1. Run the configurator and let it generate `RVSconfig.yml` (offered after
   `cloud-init.yaml`).
2. SSH into the server and run:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/PhilippWu/RemoteVibeServer/main/install.sh | sudo bash
   ```

3. Paste the contents of `RVSconfig.yml` when prompted, then press **Ctrl-D**.

The script parses the YAML into `/etc/dev-server/env`, installs Docker, UFW,
fail2ban, and downloads the provisioning scripts — then runs `setup.sh`
automatically.

## Step 3: Wait for Provisioning

Provisioning takes approximately **3–8 minutes** depending on server specs and network speed.

### Monitor Progress

```bash
# SSH into the server
ssh root@<SERVER_IP>

# Watch the provisioning log
tail -f /var/log/dev-server-provision.log
```

### Check cloud-init status

```bash
cloud-init status --wait
```

## Step 4: Validate the Deployment

### Automated Checks

```bash
# On the server:
cat /etc/dev-server/status
```

Expected output:
```
provisioned_at=2024-01-15T10:30:00Z
fqdn=dev.example.com
public_ip=1.2.3.4
coder_url=https://dev.example.com
coder_status=active
caddy_status=active
```

### Manual Checks

| Check                        | Command / Action                                          |
|------------------------------|-----------------------------------------------------------|
| DNS resolves correctly       | `dig dev.example.com` → should show your server's IP      |
| HTTPS works                  | `curl -I https://dev.example.com` → 200 or 307            |
| Valid TLS certificate        | `openssl s_client -connect dev.example.com:443`            |
| Coder is running             | `systemctl status coder`                                   |
| Caddy is running             | `systemctl status caddy`                                   |
| Firewall is active           | `ufw status`                                               |

### Access Coder Web UI

1. Open `https://dev.example.com` in your browser
2. Log in with the admin credentials — username is the email you configured, password is `CODER_ADMIN_PASSWORD` (or check `/etc/dev-server/env` on the server if it was auto-generated)
3. Create a workspace using the pre-installed Docker template
4. Click **"VS Code Web"** in the workspace card to open VS Code directly in the browser

## Step 5: Connect VS Code Desktop

### Via Coder CLI (Recommended)

```bash
# Install Coder CLI locally
curl -fsSL https://coder.com/install.sh | sh

# Login
coder login https://dev.example.com

# List workspaces
coder ls

# Connect via SSH
coder ssh my-workspace

# Or: configure SSH for VS Code Remote
coder config-ssh
# Then open VS Code → Remote-SSH → select "coder.my-workspace"
```

### Via Direct SSH

Coder configures SSH automatically. After `coder config-ssh`, your `~/.ssh/config` will have entries like:

```
Host coder.my-workspace
    HostName coder.my-workspace
    ProxyCommand coder ssh --stdio my-workspace
    ...
```

Open VS Code → Remote-SSH → connect to `coder.my-workspace`.

## Step 6: (Optional) Configure AI Agents

If you enabled AI agents during provisioning, verify they are available:

```bash
# In a Coder workspace terminal:
which github-copilot-cli   # if ENABLE_AGENT_COPILOT=true
which claude               # if ENABLE_AGENT_CLAUDE=true
which codex                # if ENABLE_AGENT_CODEX=true
which opencode             # if ENABLE_AGENT_OPENCODE=true
```

## Step 7: (Optional) Starter App Templates

RemoteVibeServer can automatically bootstrap a production-ready starter
application inside every new Coder workspace.

### Available templates

| Value               | Description                                                |
|---------------------|------------------------------------------------------------|
| `none`              | No template — plain workspace (default)                    |
| `fullstack-baseline`| FastAPI + PostgreSQL + React/Vite + Auth + RBAC (tiangolo) |

### Enabling a template

Set `STARTER_TEMPLATE` in `/etc/dev-server/env` **before** provisioning:

```yaml
# In RVSconfig.yml / cloud-init.yaml:
STARTER_TEMPLATE: "fullstack-baseline"
```

Or via the configurator CLI — a new step `Starter App Template` appears after
the AI Agents step.

### What fullstack-baseline provides

Based on **[tiangolo/full-stack-fastapi-template](https://github.com/tiangolo/full-stack-fastapi-template)**:

- **FastAPI** backend (Python, SQLModel, Alembic migrations)
- **PostgreSQL 16** database
- **React + Vite** frontend (TypeScript, Chakra UI)
- JWT auth + RBAC (superuser / regular-user roles)
- Docker Compose stack — starts automatically on workspace launch

**Default ports inside the workspace:**

| Service          | URL                               |
|------------------|-----------------------------------|
| Frontend         | http://localhost:5173             |
| Backend API      | http://localhost:8000             |
| Interactive docs | http://localhost:8000/docs        |

**Default credentials:** `admin@example.com` / `changeme123` (change on first login)

### Template lifecycle

- The stack is cloned and started on the **first workspace launch** (~2 min)
- Subsequent starts run `docker compose up -d` (fast — containers already exist)
- A `.bootstrapped` marker prevents re-cloning; local edits persist across restarts
- Remove `.bootstrapped` and restart the workspace to reset to a clean clone

For full documentation see [`templates/fullstack-baseline/README.md`](../../templates/fullstack-baseline/README.md).

## Troubleshooting

### Provisioning failed

```bash
# Check the full log
cat /var/log/dev-server-provision.log

# Check cloud-init logs
cat /var/log/cloud-init-output.log
journalctl -u cloud-init
```

### DNS not resolving

```bash
# Check the Cloudflare record was created
dig dev.example.com @1.1.1.1

# If not, re-run DNS setup
source /etc/dev-server/env
bash /opt/dev-server-provision/infra/dns.sh
```

### HTTPS certificate errors

```bash
# Check Caddy logs
journalctl -u caddy --no-pager -n 50

# Caddy needs port 80 open for ACME challenge
ufw status | grep 80
```

### Coder not starting

```bash
systemctl status coder
journalctl -u coder --no-pager -n 50

# Ensure Docker is running
systemctl status docker
```

### Re-running provisioning

All scripts are idempotent. To re-provision:

```bash
FORCE_DOWNLOAD=true /etc/dev-server/bootstrap.sh 2>&1 | tee /var/log/dev-server-provision.log
```

## Updating

### Update Coder

```bash
curl -fsSL https://coder.com/install.sh | sh -s -- --method=standalone
systemctl restart coder
```

### Update Caddy

```bash
apt-get update && apt-get install --only-upgrade caddy
systemctl restart caddy
```

### Update provisioning scripts

```bash
FORCE_DOWNLOAD=true /etc/dev-server/bootstrap.sh
```
