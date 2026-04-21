terraform {
  required_providers {
    coder = {
      source = "coder/coder"
    }
    docker = {
      source = "kreuzwerker/docker"
    }
  }
}

locals {
  username = data.coder_workspace_owner.me.name
}

variable "docker_socket" {
  default     = ""
  description = "(Optional) Docker socket URI"
  type        = string
}

provider "docker" {
  host = var.docker_socket != "" ? var.docker_socket : null
}

data "coder_provisioner" "me" {}
data "coder_workspace" "me" {}
data "coder_workspace_owner" "me" {}

resource "coder_agent" "main" {
  arch = data.coder_provisioner.me.arch
  os   = "linux"

  # Source agent API keys and persist them to the shell profile.
  # Keys come from /run/secrets/agent-env (bind-mounted read-only from host).
  startup_script = <<-EOT
    set -e

    # Prepare user home with default files on first start.
    if [ ! -f ~/.init_done ]; then
      cp -rT /etc/skel ~ 2>/dev/null || true
      touch ~/.init_done
    fi

    # Load AI agent API keys from bind-mounted secret file.
    AGENT_ENV=/run/secrets/agent-env
    if [ -f "$AGENT_ENV" ]; then
      while IFS='=' read -r key value; do
        [[ "$key" =~ ^#.*$ || -z "$key" ]] && continue
        export "$key=$value"
        grep -qF "export $key=" ~/.bashrc 2>/dev/null \
          || echo "export $key=\"$value\"" >> ~/.bashrc
      done < "$AGENT_ENV"
      echo "[remotevibe] Agent API keys loaded from $AGENT_ENV"
    else
      echo "[remotevibe] WARNING: $AGENT_ENV not found — AI agents may not be authenticated"
    fi
    # ── Configure Coder CLI for workspace template management ────────────────
    if [ -f /run/secrets/coder-token ]; then
      _tok=$(cat /run/secrets/coder-token | tr -d '[:space:]')
      export CODER_SESSION_TOKEN=$_tok
      grep -qxF "export CODER_SESSION_TOKEN=$_tok" ~/.bashrc 2>/dev/null \
        || echo "export CODER_SESSION_TOKEN=$_tok" >> ~/.bashrc
      echo "[remotevibe] Coder CLI configured — ~/push-template.sh available"
    fi
    # ── Start Docker daemon (no-op when DEV_TOOLS does not include "docker") ─
    if command -v start-dockerd >/dev/null 2>&1; then
      sudo start-dockerd \
        || echo "[remotevibe] WARNING: start-dockerd failed — Docker inside the workspace may not work. Check /var/log/dockerd.log for details and ensure the workspace container is running with privileged: true."
    fi
    # ── Start code-server (VS Code in browser) ──────────────────────────────
    code-server \
      --auth none \
      --port 13337 \
      --bind-addr 0.0.0.0:13337 \
      >/tmp/code-server.log 2>&1 &

    echo "[remotevibe] Workspace ready! VS Code: \$CODER_URL/@${local.username}/${data.coder_workspace.me.name}/apps/code-server/"
  EOT

  env = {
    GIT_AUTHOR_NAME     = coalesce(data.coder_workspace_owner.me.full_name, data.coder_workspace_owner.me.name)
    GIT_AUTHOR_EMAIL    = "${data.coder_workspace_owner.me.email}"
    GIT_COMMITTER_NAME  = coalesce(data.coder_workspace_owner.me.full_name, data.coder_workspace_owner.me.name)
    GIT_COMMITTER_EMAIL = "${data.coder_workspace_owner.me.email}"
  }

  metadata {
    display_name = "CPU Usage"
    key          = "0_cpu_usage"
    script       = "coder stat cpu"
    interval     = 10
    timeout      = 1
  }

  metadata {
    display_name = "RAM Usage"
    key          = "1_ram_usage"
    script       = "coder stat mem"
    interval     = 10
    timeout      = 1
  }

  metadata {
    display_name = "Home Disk"
    key          = "3_home_disk"
    script       = "coder stat disk --path $${HOME}"
    interval     = 60
    timeout      = 1
  }

  metadata {
    display_name = "CPU Usage (Host)"
    key          = "4_cpu_usage_host"
    script       = "coder stat cpu --host"
    interval     = 10
    timeout      = 1
  }

  metadata {
    display_name = "Memory Usage (Host)"
    key          = "5_mem_usage_host"
    script       = "coder stat mem --host"
    interval     = 10
    timeout      = 1
  }

  metadata {
    display_name = "Load Average (Host)"
    key          = "6_load_host"
    script       = <<EOT
      echo "`cat /proc/loadavg | awk '{ print $1 }'` `nproc`" | awk '{ printf "%0.2f", $1/$2 }'
    EOT
    interval     = 60
    timeout      = 1
  }

  metadata {
    display_name = "Swap Usage (Host)"
    key          = "7_swap_host"
    script       = <<EOT
      free -b | awk '/^Swap/ { printf("%.1f/%.1f", $3/1024.0/1024.0/1024.0, $2/1024.0/1024.0/1024.0) }'
    EOT
    interval     = 10
    timeout      = 1
  }
}

resource "coder_app" "code_server" {
  agent_id     = coder_agent.main.id
  slug         = "code-server"
  display_name = "VS Code"
  url          = "http://localhost:13337/?folder=/home/coder"
  icon         = "/icon/code.svg"
  subdomain    = false
  share        = "owner"

  healthcheck {
    url       = "http://localhost:13337/healthz"
    interval  = 5
    threshold = 6
  }
}

resource "docker_volume" "home_volume" {
  name = "coder-${data.coder_workspace.me.id}-home"
  lifecycle {
    ignore_changes = all
  }
  labels {
    label = "coder.owner"
    value = data.coder_workspace_owner.me.name
  }
  labels {
    label = "coder.owner_id"
    value = data.coder_workspace_owner.me.id
  }
  labels {
    label = "coder.workspace_id"
    value = data.coder_workspace.me.id
  }
  labels {
    label = "coder.workspace_name_at_creation"
    value = data.coder_workspace.me.name
  }
}

# Persistent Docker data volume so images / containers / volumes built inside
# the workspace survive restarts.  Used only when Docker is enabled in the
# workspace image (DEV_TOOLS contains "docker"); otherwise the volume sits
# unused at negligible cost.
resource "docker_volume" "docker_data_volume" {
  name = "coder-${data.coder_workspace.me.id}-docker"
  lifecycle {
    ignore_changes = all
  }
  labels {
    label = "coder.owner"
    value = data.coder_workspace_owner.me.name
  }
  labels {
    label = "coder.workspace_id"
    value = data.coder_workspace.me.id
  }
}

# Use locally-built image — keep_locally prevents pulling from Docker Hub
resource "docker_image" "workspace" {
  name         = "remotevibe-workspace:latest"
  keep_locally = true
}

resource "docker_container" "workspace" {
  count    = data.coder_workspace.me.start_count
  image    = docker_image.workspace.image_id
  name     = "coder-${data.coder_workspace_owner.me.name}-${lower(data.coder_workspace.me.name)}"
  hostname = data.coder_workspace.me.name

  # Required so dockerd can start inside the workspace (Docker dev-tool support).
  # The container bounding set must include CAP_SYS_ADMIN / CAP_NET_ADMIN —
  # privileged mode is the only way to grant these from a non-root userns.
  privileged = true

  # replace() ensures the agent can reach Coder even when the access URL uses localhost/127.0.0.1
  entrypoint = ["sh", "-c", replace(coder_agent.main.init_script, "/localhost|127\\.0\\.0\\.1/", "host.docker.internal")]

  env = [
    "CODER_AGENT_TOKEN=${coder_agent.main.token}",
    "CODER_URL=${data.coder_workspace.me.access_url}",
    "CODER_TEMPLATE_NAME=remotevibe",
    "CODER_TEMPLATE_DIR=/workspace/template",
  ]

  host {
    host = "host.docker.internal"
    ip   = "host-gateway"
  }

  volumes {
    container_path = "/home/coder"
    volume_name    = docker_volume.home_volume.name
    read_only      = false
  }

  # Persistent Docker data — pulled images and containers survive restarts.
  volumes {
    container_path = "/var/lib/docker"
    volume_name    = docker_volume.docker_data_volume.name
    read_only      = false
  }

  # Agent API keys — bind-mount read-only from host.
  # Contains only: GITHUB_TOKEN, OPENAI_API_KEY, ANTHROPIC_API_KEY,
  #                GOOGLE_API_KEY, OPENCODE_PROVIDER
  volumes {
    container_path = "/run/secrets/agent-env"
    host_path      = "/etc/dev-server/agent-env"
    read_only      = true
  }

  # Coder CLI binary from host — enables `coder` command inside the workspace.
  volumes {
    container_path = "/usr/local/bin/coder"
    host_path      = "/usr/local/bin/coder"
    read_only      = true
  }

  # Workspace template source (read-write) — agents can edit and push updates.
  volumes {
    container_path = "/workspace/template"
    host_path      = "/opt/dev-server-provision/coder"
    read_only      = false
  }

  # Long-lived admin token for Coder CLI authentication inside the workspace.
  volumes {
    container_path = "/run/secrets/coder-token"
    host_path      = "/etc/dev-server/coder-admin-token"
    read_only      = true
  }

  labels {
    label = "coder.owner"
    value = data.coder_workspace_owner.me.name
  }
  labels {
    label = "coder.owner_id"
    value = data.coder_workspace_owner.me.id
  }
  labels {
    label = "coder.workspace_id"
    value = data.coder_workspace.me.id
  }
  labels {
    label = "coder.workspace_name"
    value = data.coder_workspace.me.name
  }
}
