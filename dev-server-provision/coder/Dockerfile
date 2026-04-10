# syntax=docker/dockerfile:1
# =============================================================================
# Coder Workspace Image — RemoteVibeServer
# =============================================================================
# A feature-rich development container suitable for use as a Coder workspace
# template.  Includes common development tools pre-installed.
#
# Build:
#   docker build -t remotevibe-workspace:latest .
# =============================================================================
FROM codercom/enterprise-base:ubuntu

USER root

# ---------------------------------------------------------------------------
# System packages
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    wget \
    git \
    jq \
    unzip \
    zip \
    htop \
    tree \
    ripgrep \
    fd-find \
    bat \
    vim \
    neovim \
    tmux \
    openssh-client \
    gnupg \
    ca-certificates \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Docker CLI (for Docker-in-Docker / Docker-outside-Docker workflows)
# ---------------------------------------------------------------------------
RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
       | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
       https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
       > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Node.js 20 LTS
# ---------------------------------------------------------------------------
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Go (latest stable)
# ---------------------------------------------------------------------------
ARG GO_VERSION=1.22.2
RUN curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" \
    | tar -C /usr/local -xz
ENV PATH="/usr/local/go/bin:${PATH}"

# ---------------------------------------------------------------------------
# Rust (via rustup, for coder user)
# ---------------------------------------------------------------------------
USER coder
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y --default-toolchain stable
ENV PATH="/home/coder/.cargo/bin:${PATH}"

# ---------------------------------------------------------------------------
# GitHub CLI (for gh copilot extension)
# ---------------------------------------------------------------------------
USER root
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
       > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# AI Coding Agent CLIs
# Keys are NOT baked into the image — injected at runtime via /run/secrets/agent-env
# ---------------------------------------------------------------------------
RUN npm install -g \
      @anthropic-ai/claude-code \
      @openai/codex \
      opencode-ai \
      @githubnext/github-copilot-cli \
    2>/dev/null || true

# Install gh copilot extension for the coder user (requires GITHUB_TOKEN at runtime)
USER coder
RUN GITHUB_TOKEN=placeholder gh extension install github/gh-copilot 2>/dev/null || true

# ---------------------------------------------------------------------------
# code-server — VS Code in the browser
# ---------------------------------------------------------------------------
USER root
RUN curl -fsSL https://code-server.dev/install.sh | sh

# ---------------------------------------------------------------------------
# Coder CLI placeholder (actual binary bind-mounted from host at runtime)
# /workspace/template is the mount point for the template source.
# ---------------------------------------------------------------------------
USER root
RUN touch /usr/local/bin/coder && chmod +x /usr/local/bin/coder \
    && mkdir -p /workspace/template

# ---------------------------------------------------------------------------
# Workspace context files for AI agents
# Placed in /etc/skel/ — startup_script copies them to ~/ on first workspace start.
# ---------------------------------------------------------------------------
RUN <<'EOF'
set -e
mkdir -p /etc/skel

cat > /etc/skel/REMOTEVIBE.md << 'MDEOF'
# RemoteVibe Workspace — AI Agent Context

You are running inside a **Coder workspace** on the RemoteVibe self-hosted dev server.

## Environment

| Variable              | Description                                         |
|-----------------------|-----------------------------------------------------|
| `CODER_URL`           | Coder server URL                                    |
| `CODER_SESSION_TOKEN` | Admin API token (set by startup script)             |
| `CODER_TEMPLATE_NAME` | `remotevibe`                                        |
| `CODER_TEMPLATE_DIR`  | `/workspace/template`                               |

AI agent keys (`GITHUB_TOKEN`, `OPENAI_API_KEY`, etc.) are in `/run/secrets/agent-env`.

## VS Code in Browser

A full VS Code web interface is available via the **"VS Code"** button in the Coder
workspace dashboard, or directly at:

```
$CODER_URL/@<owner>/<workspace>/apps/code-server/
```

code-server runs on port 13337 inside the container (no auth — Coder handles that).

## What is Coder?

Coder is a remote development platform. This workspace is a Docker container
provisioned by a Terraform template called **remotevibe**. You can modify the
template and push updates to Coder without leaving this workspace.

## Template Files

The template is bind-mounted at `/workspace/template/` (read-write):

- `main.tf`           — Terraform config (container, volumes, agent, mounts)
- `Dockerfile`        — Docker image for this workspace (rebuilt on push)
- `devcontainer.json` — Dev container metadata

## Modifying the Template

```bash
# 1. Edit the template
nano /workspace/template/main.tf
# or edit the Dockerfile:
nano /workspace/template/Dockerfile

# 2. Push the updated template (Coder CLI is pre-authenticated)
~/push-template.sh
```

Or call `coder` directly:

```bash
coder templates push remotevibe --directory /workspace/template --yes
```

## Coder CLI (pre-authenticated)

The `coder` CLI is available and pre-authenticated via `CODER_SESSION_TOKEN`.

```bash
coder templates list                                              # list all templates
coder templates versions remotevibe                              # version history
coder templates push remotevibe --directory /workspace/template  # push an update
coder workspaces list                                            # list workspaces
```

## Notes

- Template changes take effect for **new** workspaces or after a workspace restart
- Changing the Dockerfile triggers an image rebuild on the next template push
- The startup script runs on every workspace start
MDEOF

cat > /etc/skel/push-template.sh << 'SHEOF'
#!/bin/bash
# RemoteVibe: Push the updated workspace template to Coder.
# Edit /workspace/template/main.tf (and Dockerfile), then run this script.
set -e
# Explicitly load token so this works in non-interactive shells (e.g. AI agents).
if [[ -z "${CODER_SESSION_TOKEN:-}" ]]; then
  export CODER_SESSION_TOKEN="$(cat /run/secrets/coder-token 2>/dev/null | tr -d '[:space:]')"
fi
if [[ -z "${CODER_SESSION_TOKEN:-}" ]]; then
  echo "ERROR: CODER_SESSION_TOKEN is not set and /run/secrets/coder-token is empty."
  echo "Run: coder login \$CODER_URL"
  exit 1
fi
echo "==> Pushing remotevibe template to Coder..."
coder templates push remotevibe --directory /workspace/template --yes
echo "==> Done! New workspaces will use the updated template."
echo "    To apply changes to THIS workspace: stop and restart it."
SHEOF
chmod +x /etc/skel/push-template.sh
EOF

# ---------------------------------------------------------------------------
# Workspace defaults
# ---------------------------------------------------------------------------
WORKDIR /home/coder
USER coder
