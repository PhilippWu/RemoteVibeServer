#!/usr/bin/env bash
# =============================================================================
# bootstrap.sh — Entry-point for RemoteVibeServer provisioning
# =============================================================================
# Loads the secure environment file and delegates to setup.sh.
#
# This script is designed to be:
#   • Downloaded and executed by cloud-init on first boot
#   • Idempotent — safe to re-run at any time
#   • Self-contained — only depends on bash, curl, and the env file
# =============================================================================
set -euo pipefail

# Suppress interactive prompts from apt/dpkg and needrestart during provisioning.
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a

# cloud-init runcmd runs without a login shell — HOME is not set.
export HOME="${HOME:-/root}"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ENV_FILE="/etc/dev-server/env"
PROVISION_DIR="/opt/dev-server-provision"
LOG_FILE="/var/log/dev-server-provision.log"
REPO_URL="https://raw.githubusercontent.com/PhilippWu/RemoteVibeServer/main/dev-server-provision"

# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------
log() {
  local ts
  ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "[$ts] [bootstrap] $*" | tee -a "$LOG_FILE"
}

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
  echo "ERROR: bootstrap.sh must be run as root." >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: Environment file not found at $ENV_FILE" >&2
  echo "       Create it from cloud-init.example.yaml first." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Load environment
# ---------------------------------------------------------------------------
log "Loading environment from $ENV_FILE"
set -a
# shellcheck source=/dev/null
source "$ENV_FILE"
set +a

# ---------------------------------------------------------------------------
# Download provisioning scripts (idempotent)
# ---------------------------------------------------------------------------
mkdir -p "$PROVISION_DIR/infra" "$PROVISION_DIR/coder"

log "Downloading provisioning scripts from $REPO_URL …"
for f in setup.sh infra/dns.sh infra/proxy.sh infra/agents.sh coder/Dockerfile coder/devcontainer.json; do
  target="$PROVISION_DIR/$f"
  if [[ ! -f "$target" ]] || [[ "${FORCE_DOWNLOAD:-false}" == "true" ]]; then
    curl -fsSL "$REPO_URL/$f" -o "$target"
    log "  ✓ $f"
  else
    log "  ⏭ $f (already present)"
  fi
done

chmod +x "$PROVISION_DIR/setup.sh" "$PROVISION_DIR/infra/"*.sh

# ---------------------------------------------------------------------------
# Execute setup
# ---------------------------------------------------------------------------
log "Handing off to setup.sh …"
exec "$PROVISION_DIR/setup.sh"
