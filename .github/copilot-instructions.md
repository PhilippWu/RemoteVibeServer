# Copilot Instructions — RemoteVibeServer

> **Self-onboarding document for GitHub Copilot.**
> Read this fully before making any changes. It captures architecture decisions,
> dev workflow, known gotchas, and the current state of the project.

---

## What is RemoteVibeServer?

A fully automated, one-shot deployable **self-hosted remote development environment**
running on a bare Hetzner VPS. One cloud-init YAML file boots a server that automatically:

1. Installs Docker, Caddy, Coder (remote IDE platform)
2. Creates a Cloudflare DNS A record pointing `dev.nerdfactory.me` at the server IP
3. Gets a Let's Encrypt TLS certificate via Caddy
4. Builds a Docker workspace image with AI coding agents pre-installed
5. Pushes the default Coder workspace template (`remotevibe`)
6. Creates the Coder admin user with a configurable password
7. Starts code-server (VS Code in browser) inside every workspace

**Domain:** `dev.nerdfactory.me`
**Coder admin email:** `phwurzer@gmail.com`
**Coder admin username:** `admin`
**SSH key:** `C:\Users\phili\.ssh\UplandApp_Hetzner` (for `root@<server-ip>`)

---

## Repository Structure

```
RemoteVibeServer/
├── .github/
│   └── copilot-instructions.md     ← you are here
├── dev-server-provision/
│   ├── setup.sh                    ← main orchestration (runs on server at boot)
│   ├── bootstrap.sh                ← thin bootstrap downloaded first by cloud-init
│   ├── cloud-init.yaml             ← NEVER commit — contains secrets
│   ├── cloud-init.example.yaml     ← safe example (no secrets)
│   ├── RVSconfig.yml               ← configurator input schema
│   ├── infra/
│   │   ├── dns.sh                  ← Cloudflare DNS A record creation
│   │   ├── proxy.sh                ← Caddy setup (maintenance page → live proxy)
│   │   └── agents.sh               ← optional AI agent CLIs (host-level)
│   ├── coder/
│   │   ├── main.tf                 ← Terraform template for Docker workspace containers
│   │   ├── Dockerfile              ← workspace Docker image
│   │   └── devcontainer.json       ← dev container metadata
│   ├── configurator/               ← cross-platform CLI to generate cloud-init.yaml
│   └── docs/                       ← architecture, security, deployment docs
└── README.md
```

**`cloud-init.yaml` is gitignored** — it contains Cloudflare tokens, the admin
password, and GitHub tokens. Use `cloud-init.example.yaml` as a template.

---

## Architecture

```
Internet
  │  HTTPS (443)
  ▼
Cloudflare (DNS proxy, DDoS protection)
  │
  ▼
Hetzner VPS (Ubuntu)
  ├── UFW firewall (22, 80, 443 only)
  ├── fail2ban
  ├── Caddy (reverse proxy + auto TLS)  :80/:443 → Coder :3000
  ├── Coder server (systemd)  :3000 (localhost only)
  │     └── workspace provisioner (Docker provider)
  └── Docker
        └── coder-<owner>-<workspace> containers
              ├── code-server (VS Code)  :13337
              ├── AI agents (Copilot CLI, OpenCode, etc.)
              └── Coder agent (WebSocket back to Coder server)
```

**Key design decisions:**
- Coder listens only on `127.0.0.1:3000` — Caddy is the only public entry point
- Workspace containers use Docker-outside-Docker (DooD): the host Docker socket
  is NOT mounted; `docker-ce-cli` inside the container is just for developer use
- Cloudflare proxying is enabled (`proxied: true`) — the real server IP is hidden
- Secrets flow: `cloud-init.yaml` → `/etc/dev-server/env` (0600) → read by systemd
  unit and setup.sh scripts. Never in the repo.

---

## The Coder Workspace Template (`remotevibe`)

The template defines what every workspace container looks like.

### Files that define the template (`dev-server-provision/coder/`)

| File | Role |
|------|------|
| `main.tf` | Terraform config — Docker container, volumes, env vars, coder_app resources |
| `Dockerfile` | Docker image built during provisioning — cached as `remotevibe-workspace:latest` |
| `devcontainer.json` | Dev container metadata (for VS Code devcontainer protocol) |

### What's inside each workspace container

- **Languages:** Python 3, Node.js 20 LTS, Go 1.22, Rust (stable)
- **Tools:** git, gh CLI, docker-ce-cli, ripgrep, bat, tmux, neovim, vim
- **AI Agents:** Claude Code, OpenAI Codex, OpenCode, GitHub Copilot CLI
- **VS Code:** `code-server` on port 13337 (browser-accessible via Coder dashboard)
- **Coder CLI:** bind-mounted from host `/usr/local/bin/coder` (read-only)

### Bind mounts into each workspace container

| Container path | Host path | Mode | Purpose |
|---|---|---|---|
| `/home/coder` | Docker volume | rw | Persistent home directory |
| `/usr/local/bin/coder` | `/usr/local/bin/coder` | ro | Coder CLI binary |
| `/workspace/template` | `/opt/dev-server-provision/coder` | rw | Template source — agents can edit & push |
| `/run/secrets/coder-token` | `/etc/dev-server/coder-admin-token` | ro | Long-lived Coder admin API token |
| `/run/secrets/agent-env` | `/etc/dev-server/agent-env` | ro | AI agent API keys |

### Template-editing capability (for AI agents in workspaces)

Agents inside a workspace can modify and push the template:

```bash
# Edit template files
nano /workspace/template/main.tf
nano /workspace/template/Dockerfile

# Push update (script handles auth automatically)
~/push-template.sh
```

`CODER_SESSION_TOKEN` is pre-set in the shell from `/run/secrets/coder-token`.
`push-template.sh` explicitly loads the token from the file if the env var is empty
(needed for non-interactive shells used by AI agents).

**`REMOTEVIBE.md`** in every workspace home directory gives AI agents full context
about the environment (equivalent of this document, workspace-scoped).

---

## Dev Workflow

### Making changes to provisioning scripts

1. Edit files in `dev-server-provision/` locally
2. Commit and push to `main`
3. The next server deployment picks up changes automatically (bootstrap downloads from GitHub)

### Making changes to the Coder workspace template

**Option A — via a running workspace (preferred for template-only changes):**
```bash
# Inside the workspace:
nano /workspace/template/main.tf  # or Dockerfile
~/push-template.sh                # pushes to Coder; rebuilds image if Dockerfile changed
# Restart the workspace in Coder UI to pick up changes
```

**Option B — via SSH to the server:**
```bash
ssh -i C:\Users\phili\.ssh\UplandApp_Hetzner root@<server-ip>
nano /opt/dev-server-provision/coder/main.tf
CODER_URL=http://127.0.0.1:3000 CODER_SESSION_TOKEN=$(cat /etc/dev-server/coder-admin-token) \
  coder templates push remotevibe --directory /opt/dev-server-provision/coder --yes
```

**Option C — commit to repo, then pull on server:**
```bash
ssh root@<server-ip> "cd /opt/dev-server-provision && git pull"
# then push template as in Option B
```

### Deploying a new server

1. Edit `dev-server-provision/cloud-init.yaml` with new server IP/domain/credentials
2. Create a new Hetzner VPS with Ubuntu 22.04, paste cloud-init content
3. Monitor: `ssh root@<ip> "tail -f /var/log/dev-server-provision.log"`
4. Provisioning takes ~5–10 minutes. `dev.nerdfactory.me` should be live after Caddy starts.

---

## Known Gotchas & Hard-Won Knowledge

### Coder API token endpoint
**Correct:** `POST /api/v2/users/me/keys/tokens` (returns `{"key":"..."}`)
**Wrong:** `POST /api/v2/users/me/tokens` → HTTP 404 on Coder v2.31.9

### Docker bind-mount directory creation bug
If a bind-mount `host_path` doesn't exist when `docker run` executes, Docker silently
creates it as an **empty directory**. This means `echo "token" > /etc/dev-server/coder-admin-token`
fails with `Is a directory` on the next attempt.

**Fix (already in setup.sh):** `touch /etc/dev-server/coder-admin-token && chmod 0644` before
Docker ever starts.

### Token file permissions: must be 0644, not 0600
The workspace container runs as user `coder` (uid=1000). A `0600 root:root` file on the
host is unreadable inside the container. Use `0644` — container isolation is the security boundary.

### bash -lc in non-interactive docker exec
`docker exec --user coder container bash -lc "..."` does NOT fully source `.bashrc`
because Ubuntu's default `.bashrc` has `[ -z "$PS1" ] && return` near the top (exits
early for non-interactive shells). Env vars set in `.bashrc` are NOT available.
**Fix:** `push-template.sh` and similar scripts explicitly `cat /run/secrets/coder-token`.

### Coder container naming convention
Containers are named `coder-<owner>-<workspace>` (lowercase).
E.g., owner=`admin`, workspace=`test` → container name = `coder-admin-test`.

### Coder login via API (no CLI flags)
`coder login` has no `--email`/`--password` flags. Use the API directly:
```bash
TOK=$(curl -sf -X POST http://127.0.0.1:3000/api/v2/users/login \
  -H "Content-Type: application/json" \
  -d '{"email":"phwurzer@gmail.com","password":"<PASS>"}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['session_token'])")
```

### code-server in main.tf startup_script
The `&` at end of `code-server ... &` is inside a Terraform heredoc. This is fine —
the startup script runs in a bash subshell and `&` backgrounds the process correctly.

### replace() in container entrypoint
```hcl
entrypoint = ["sh", "-c", replace(coder_agent.main.init_script, "/localhost|127\\.0\\.0\\.1/", "host.docker.internal")]
```
This is required because the Coder agent init script contains the access URL, which
during local testing may be `localhost`. Without this replace, the agent inside the
Docker container can't reach the Coder server on the host.

---

## Current Feature State (as of commit 2f359b5)

| Feature | Status |
|---------|--------|
| Cloud-init one-shot provisioning | ✅ |
| Cloudflare DNS automation | ✅ |
| Caddy HTTPS + maintenance page | ✅ |
| Coder v2 install + admin user creation | ✅ |
| Docker workspace image build | ✅ |
| Coder template push on first boot | ✅ |
| Long-lived admin token for workspace agents | ✅ |
| VS Code in browser (code-server) | ✅ |
| AI agents in workspace (Copilot, OpenCode) | ✅ |
| Template editing from inside workspace | ✅ |
| `REMOTEVIBE.md` AI agent context doc | ✅ |
| `push-template.sh` non-interactive helper | ✅ |
| Interactive configurator CLI | ✅ |

---

## File Locations on the Running Server

| Path | Contents |
|------|----------|
| `/etc/dev-server/env` | All secrets (Cloudflare token, Coder password, GitHub token) |
| `/etc/dev-server/coder-admin-token` | Long-lived Coder admin API token (0644) |
| `/etc/dev-server/agent-env` | AI agent API keys injected into workspace containers |
| `/etc/dev-server/status` | Deployment status written by setup.sh |
| `/opt/dev-server-provision/` | All provisioning scripts (cloned/downloaded from repo) |
| `/opt/dev-server-provision/coder/` | Coder template files (main.tf, Dockerfile, etc.) |
| `/var/log/dev-server-provision.log` | Full provisioning log |
| `/etc/caddy/Caddyfile` | Live Caddy config |
| `/etc/systemd/system/coder.service` | Coder systemd unit |

---

## Secrets Management

**Never commit `cloud-init.yaml`** — it is gitignored. The file contains:
- `CLOUDFLARE_API_TOKEN` — Cloudflare API token for DNS management
- `CLOUDFLARE_ZONE_ID` — Cloudflare zone for `nerdfactory.me`
- `CODER_ADMIN_PASSWORD` — Coder admin password (≥8 chars, no spaces)
- `GITHUB_TOKEN` — GitHub PAT for Copilot/gh CLI in workspaces
- Various AI API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.)

Use `cloud-init.example.yaml` as a template — it has all the fields with placeholder values.

The configurator (`dev-server-provision/configurator/`) generates `cloud-init.yaml` interactively.

---

## Useful Commands (on the server)

```bash
# Check provisioning log
tail -f /var/log/dev-server-provision.log

# Check Coder service
systemctl status coder

# List running workspace containers
docker ps --format "table {{.Names}}\t{{.Status}}"

# Get a Coder session token (for manual API calls)
TOK=$(curl -sf -X POST http://127.0.0.1:3000/api/v2/users/login \
  -H "Content-Type: application/json" \
  -d '{"email":"phwurzer@gmail.com","password":"<pass>"}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['session_token'])")

# Push template update manually
CODER_URL=http://127.0.0.1:3000 CODER_SESSION_TOKEN=$TOK \
  coder templates push remotevibe --directory /opt/dev-server-provision/coder --yes

# Rebuild workspace image
docker build -t remotevibe-workspace:latest /opt/dev-server-provision/coder

# Exec into a workspace container
docker exec -it --user coder coder-admin-test bash
```
