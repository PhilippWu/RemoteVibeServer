# syntax=docker/dockerfile:1
# =============================================================================
# Coder Workspace Image — RemoteVibeServer
# =============================================================================
# A feature-rich development container suitable for use as a Coder workspace
# template.  The set of tools installed is controlled by the DEV_TOOLS build
# argument — a comma-separated list of tool keys.  Supported keys:
#
#   docker   → docker-ce engine + CLI + buildx + compose-plugin + standalone
#              docker-compose binary, "coder" added to docker group, plus the
#              /usr/local/bin/start-dockerd helper.  Requires the workspace
#              container to be run with privileged: true (set in main.tf).
#   node     → Node.js 20 LTS + npm
#   python   → python3 + pip + venv (always pulled in by base packages too)
#   go       → Go (latest stable) at /usr/local/go
#   rust     → Rust toolchain via rustup (installed for the coder user)
#   kubectl  → Kubernetes CLI
#   helm     → Helm 3
#   aws      → AWS CLI v2
#   azure    → Azure CLI
#   gcloud   → Google Cloud SDK
#
# Build:
#   docker build --build-arg DEV_TOOLS=docker,node,python -t remotevibe-workspace:latest .
# =============================================================================
FROM codercom/enterprise-base:ubuntu

USER root

# DEV_TOOLS is a comma-separated list controlling the optional installs below.
# A leading/trailing comma is added so simple substring matching ",x," works
# regardless of position.
ARG DEV_TOOLS=docker,node,python
ENV DEV_TOOLS=${DEV_TOOLS}

# ---------------------------------------------------------------------------
# Base system packages (always installed)
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
    sudo \
    apt-transport-https \
    lsb-release \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Docker (engine + CLI + compose) — gated on DEV_TOOLS containing "docker"
# Always install the CLI + compose-plugin so DooD use cases keep working when
# the workspace is run without privileged mode.  The full engine + helper
# script are only added when "docker" is selected.
# ---------------------------------------------------------------------------
RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
       | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
       https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
       > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && if echo ",${DEV_TOOLS}," | grep -q ",docker,"; then \
         apt-get install -y --no-install-recommends \
           docker-ce docker-ce-cli containerd.io \
           docker-buildx-plugin docker-compose-plugin ; \
         curl -fsSL "https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-$(uname -m)" \
           -o /usr/local/bin/docker-compose \
         && chmod +x /usr/local/bin/docker-compose ; \
         usermod -aG docker coder ; \
       else \
         apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin ; \
       fi \
    && rm -rf /var/lib/apt/lists/*

# /usr/local/bin/start-dockerd — starts dockerd inside the workspace, falling
# back to a minimal config if the container lacks full networking caps.
# Always installed; the startup_script in main.tf only invokes it when docker
# is enabled.
RUN <<'EOF'
set -e
cat > /usr/local/bin/start-dockerd <<'SHEOF'
#!/usr/bin/env bash
# RemoteVibe: start the Docker daemon inside a Coder workspace container.
# Tries full networking first; falls back to bridge=none/iptables=false when
# the container lacks the required capabilities.
set -e

if ! command -v dockerd >/dev/null 2>&1; then
  echo "[start-dockerd] dockerd not installed — skipping (DEV_TOOLS does not include 'docker')."
  exit 0
fi

if pgrep -x dockerd >/dev/null 2>&1; then
  echo "[start-dockerd] dockerd already running."
  exit 0
fi

mkdir -p /var/lib/docker /var/run

# First attempt: full networking.
nohup dockerd >/var/log/dockerd.log 2>&1 &
sleep 3
if ! pgrep -x dockerd >/dev/null 2>&1; then
  echo "[start-dockerd] full-networking dockerd failed — retrying with --bridge=none --iptables=false."
  nohup dockerd --bridge=none --iptables=false >/var/log/dockerd.log 2>&1 &
  sleep 3
fi

# Wait for the socket and relax permissions so the coder user can use docker without sudo.
for i in $(seq 1 15); do
  [ -S /var/run/docker.sock ] && break
  sleep 1
done
if [ -S /var/run/docker.sock ]; then
  chgrp docker /var/run/docker.sock 2>/dev/null || true
  chmod 660 /var/run/docker.sock 2>/dev/null || true
  echo "[start-dockerd] dockerd is up."
else
  echo "[start-dockerd] WARNING: dockerd did not produce /var/run/docker.sock — check /var/log/dockerd.log."
fi
SHEOF
chmod +x /usr/local/bin/start-dockerd
EOF

# Allow the coder user to run start-dockerd without a password prompt.
RUN echo "coder ALL=(ALL) NOPASSWD: /usr/local/bin/start-dockerd" \
      > /etc/sudoers.d/coder-dockerd \
    && chmod 0440 /etc/sudoers.d/coder-dockerd

# ---------------------------------------------------------------------------
# Node.js 20 LTS — gated on DEV_TOOLS containing "node"
# ---------------------------------------------------------------------------
RUN if echo ",${DEV_TOOLS}," | grep -q ",node,"; then \
      curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
      && apt-get install -y nodejs \
      && rm -rf /var/lib/apt/lists/* ; \
    fi

# ---------------------------------------------------------------------------
# Go (latest stable) — gated on DEV_TOOLS containing "go"
# ---------------------------------------------------------------------------
ARG GO_VERSION=1.22.2
RUN if echo ",${DEV_TOOLS}," | grep -q ",go,"; then \
      curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-$(dpkg --print-architecture).tar.gz" \
        | tar -C /usr/local -xz ; \
    fi
ENV PATH="/usr/local/go/bin:${PATH}"

# ---------------------------------------------------------------------------
# kubectl — gated on DEV_TOOLS containing "kubectl"
# ---------------------------------------------------------------------------
RUN if echo ",${DEV_TOOLS}," | grep -q ",kubectl,"; then \
      curl -fsSLo /usr/local/bin/kubectl \
        "https://dl.k8s.io/release/$(curl -fsSL https://dl.k8s.io/release/stable.txt)/bin/linux/$(dpkg --print-architecture)/kubectl" \
      && chmod +x /usr/local/bin/kubectl ; \
    fi

# ---------------------------------------------------------------------------
# Helm — gated on DEV_TOOLS containing "helm"
# ---------------------------------------------------------------------------
RUN if echo ",${DEV_TOOLS}," | grep -q ",helm,"; then \
      curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash ; \
    fi

# ---------------------------------------------------------------------------
# AWS CLI v2 — gated on DEV_TOOLS containing "aws"
# ---------------------------------------------------------------------------
RUN if echo ",${DEV_TOOLS}," | grep -q ",aws,"; then \
      arch="$(uname -m)" ; \
      curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-${arch}.zip" -o /tmp/awscli.zip \
      && unzip -q /tmp/awscli.zip -d /tmp \
      && /tmp/aws/install \
      && rm -rf /tmp/awscli.zip /tmp/aws ; \
    fi

# ---------------------------------------------------------------------------
# Azure CLI — gated on DEV_TOOLS containing "azure"
# ---------------------------------------------------------------------------
RUN if echo ",${DEV_TOOLS}," | grep -q ",azure,"; then \
      curl -fsSL https://aka.ms/InstallAzureCLIDeb | bash ; \
    fi

# ---------------------------------------------------------------------------
# Google Cloud SDK — gated on DEV_TOOLS containing "gcloud"
# ---------------------------------------------------------------------------
RUN if echo ",${DEV_TOOLS}," | grep -q ",gcloud,"; then \
      echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
        > /etc/apt/sources.list.d/google-cloud-sdk.list \
      && curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
         | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
      && apt-get update \
      && apt-get install -y --no-install-recommends google-cloud-cli \
      && rm -rf /var/lib/apt/lists/* ; \
    fi

# ---------------------------------------------------------------------------
# Rust (via rustup, for coder user) — gated on DEV_TOOLS containing "rust"
# ---------------------------------------------------------------------------
USER coder
RUN if echo ",${DEV_TOOLS}," | grep -q ",rust,"; then \
      curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
        | sh -s -- -y --default-toolchain stable ; \
    fi
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
